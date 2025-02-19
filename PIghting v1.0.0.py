from array import array
import sys
from PyQt6.QtCore import pyqtSignal, QObject, QTimer
from PyQt6.QtWidgets import QApplication, QWidget, QLineEdit, QPushButton, QTextEdit, QGridLayout, QLabel, QTableWidget, QTableWidgetItem, QStyle, QStylePainter, QColorDialog, QCheckBox
from PyQt6.QtGui import QColor 
import pickle
import time
import math
import sqlite3
import pandas as pd
import requests
import json
import os
from pathlib import Path
if sys.platform == 'linux':
        from ola.ClientWrapper import ClientWrapper

#Superclass for all widgets used by this application to facilitate error handling
class PIghtingWidget (QWidget):
        def __init__(self):
                super().__init__()
                self.errorMessage = QLineEdit()
        
        def handleError(self, error): #Update UI to handle error
                self.errorMessage.setText(str(error))
                self.errorMessage.setStyleSheet('color: red')
        
        def handleSuccess(self, success): #Update UI to handle success
                self.errorMessage.setText(success)
                self.errorMessage.setStyleSheet('color: green')
                
#Custom error called by system
class PatchError(Exception):
        def __init__(self, message):
                super().__init__(message)
                self.message = message

#Contains all relevant information of a state of the network
class Cue:
        def __init__(self, cueID, frame, fadeUp, fadeDown):
                self.ID = cueID
                self.frame = frame
                self.fadeUp = fadeUp
                self.fadeDown = fadeDown

#Used to store Cues and call various functions on cues
class  CueManager:
        def __init__(self):
                self.cueList = {}
                self.playbackPointer = 0
                #Fade times match standard initial value of 3 of ETC systems
                self._defaultFade=3

        @property
        def defaultFade(self):
                return self._defaultFade

        #Creates a new cue object and stores it in the cuelist        
        def addCue(self, cueID=None, DMXFrame=None, fadeUp=None, fadeDown=None):
                #Assigning cueID sequentially, starting from 1
                if cueID is None and len(self.cueList) == 0:
                        newCueID = 1
                elif cueID is None and len(self.cueList) > 0:
                        newCueID = max(self.cueList.keys()) + 1
                elif cueID < 0:
                       raise ValueError("Cue ID cannot be 0")
                else:
                        newCueID = cueID
                #Use an Array size 512 of all 0 if none provided
                newDMXFrame = DMXFrame if DMXFrame is not None else array('B', [0]*512)
                #Default values and more error handling
                if fadeUp is None:
                       newUp = self.defaultFade
                elif fadeUp < 0:
                       raise ValueError("Fade up time must be larger than 0")
                else:
                        newUp = fadeUp
                if fadeDown is None:
                       newDown = self.defaultFade
                elif fadeDown < 0:
                       raise ValueError("Fade down time must be larger than 0")
                else:
                        newDown = fadeDown
                #Create cue object
                newCue = Cue(newCueID, newDMXFrame, newUp, newDown)
                #Add to cue list
                self.cueList[newCue.ID] = newCue
                #Sets playback pointer to the new ID for playback functionality
                self.playbackPointer = newCueID

        #Used to find the next cue in sequence in the cue list
        def getNextCue(self):
               #Cue IDS is a dictionary, and must be sorted to determine sequence
               cueIDS = list(self.cueList.keys())
               cueIDS.sort()
               if len(cueIDS) == 0: #Checks there are cues
                      self.playbackPointer = 0
                      raise (IndexError("No cues exist")) 
               if self.playbackPointer == 0: #Checks if initial cue
                      self.playbackPointer=min(cueIDS)
                      return self.cueList[min(cueIDS)]
               playbackPosition = cueIDS.index(self.playbackPointer) # The relative position of the playbackPointer
               if playbackPosition == len(cueIDS) - 1: #Checks if final cue
                        self.playbackPointer=max(cueIDS)
                        raise IndexError('Final cue in cuelist- please use Go To Cue to return to an earlier cue')
               else: #Otherwise fetches the next cue
                        self.playbackPointer = cueIDS[playbackPosition + 1]              
               return self.cueList[self.playbackPointer]

        def getCurrentCue(self):
                cueIDS = list(self.cueList.keys())
                cueIDS.sort()
                if self.playbackPointer == 0:
                        return self.cueList[min(cueIDS)]
                else:
                        return self.cueList[self.playbackPointer]
        
        #Used to jump in the cue list
        def setPlaybackCue(self, cueID):
               self.playbackPointer = cueID

        def getPlaybackPointer(self):
                return self.playbackPointer

        def getCueList(self):
               return self.cueList
        
        #Function used for crossfading- Calculates an intermediate value 
        def interpolate(self, startValue, endValue, factor):
                 return startValue + (endValue - startValue) * factor

        #Used to calculate factor for interpolate
        def findIntermediates(self, currentFrame, nextFrame, rate, currentStep, fadeIn, fadeOut):
                fadeArray =  array( 'B' , [] ) # This empty array is populated with intermediate values
                #If the fade time is 0, this will instantly set the value to the end state
                if fadeIn == 0:
                       factorIn = 1
                else:
                        factorIn = (currentStep / (rate * fadeIn)) #Used to calculate the realtive position of the current step in relation to all fade in steps
                if factorIn > 1: #if fade in is shorter than fade down, factor in can be greater than 1, resulting in values higher than 255.
                        factorIn = 1 
                if fadeOut == 0: # Same as abouve for fade down
                       factorOut = 1
                else:
                        factorOut = (currentStep / (rate * fadeOut)) #Same as above for fading DOWN
                if factorOut > 1:
                        factorOut = 1
                for slotNo in range(len((currentFrame))):#Iterates over slots in the frame, using the correct fade  
                        if currentFrame[slotNo] > nextFrame[slotNo]:
                                intermediate = math.floor(self.interpolate(
                                        currentFrame[slotNo],
                                        nextFrame[slotNo],
                                        factorOut
                                        ))
                        if currentFrame[slotNo] < nextFrame[slotNo]:
                                intermediate = math.floor(self.interpolate(
                                        currentFrame[slotNo],
                                        nextFrame[slotNo],
                                        factorIn
                                        ))
                        if currentFrame[slotNo] == nextFrame[slotNo]:
                                intermediate = currentFrame[slotNo]
                        fadeArray.append(intermediate)
                return fadeArray

        #Used to call findIntermediates over a fixed time
        def crossFade(self, startValues, endValues, rate, fadeIn, fadeOut):
                fades = [fadeIn,fadeOut]
                maxSteps = max(fades) * rate
                if maxSteps == 0:
                       sendOLA(endValues)
                else:
                        #NOTE: Rate is simply the number of transmissions per second. It has nothing to do with the rates of change.
                        sleepTime = 1/rate
                        for step in range(maxSteps + 1):
                                currentFrame = self.findIntermediates(
                                        startValues,endValues, rate, step, fadeIn, fadeOut
                                        )
                                sendOLA(currentFrame)
                                time.sleep(sleepTime)

#Used to store fixtures and call some functions                                
class FixtureManager:
        def __init__(self):
                self.fixtureList = {}

        def addFixture(self, newFixture):
                self.fixtureList[newFixture.channelNum] = newFixture 

        def getFixtureList(self):
               return self.fixtureList

#Used to contain information about a device on a network. 
class Fixture:
    def __init__(self, fixType, attributes, DMXAddress, channelNum):
        self.type = fixType
        self.attributes = attributes
        self.address = int(DMXAddress)
        self.channelNum = int(channelNum)
        
    def setAttribute(self, data, attribute, attributeValue):
        #Account for letter case of user input
        attribute = attribute.lower()
        attributesCopy = []
        for entry in self.attributes:
                if isinstance(entry,str) is True and entry not in attributesCopy: # Assuming 8-bit resolution and no duplicates
                        attributesCopy.append(entry)
                if entry is None: # Some fixtures have null values in attributes
                        attributesCopy.append('Empty')
        attributesCopy = [x.lower() for x in attributesCopy]
        if attribute not in attributesCopy:
                 raise IndexError(f'Fixture does not have attribute {attribute}')
        #Sets appropriate slot to new value
        #DMX addressing starts from 1, 1 must be subtracted for the index
        data[self.address - 1 + attributesCopy.index(attribute)] = attributeValue
        return data

class MainWindow(PIghtingWidget):
        def __init__(self):
                super().__init__()
                self.setWindowTitle('PIghting Controller')

                ###This is for creating attributes/objects related to DMX
                # Self.data is the data CURRENTLY being outputted to OLA 
                self.data = array('B', [0]*512)
                self.cueManager = CueManager()
                self.fixtureManager = FixtureManager()
                #Fade rate chosen arbitrarily
                self.fadeRate = 50

                #---------Setting up UI---------
                ###App layout
                layout = QGridLayout()
                self.setLayout(layout)

                ###Widgets
                self.tableLabel = QLabel('Cues')
                layout.addWidget(self.tableLabel, 0, 3)

                self.cueViewer = QTableWidget()
                self.cueViewer.setColumnCount(2)
                self.columns = ['Cue #' , 'Label']
                self.cueViewer.setVerticalHeaderLabels(self.columns)
                layout.addWidget(self.cueViewer, 1,0,1,7)

                self.channelLabel = QLabel('Channel: ')
                layout.addWidget(self.channelLabel, 2, 0)
                self.inputChannel=QLineEdit('0')
                layout.addWidget(self.inputChannel, 2, 1)

                self.valueLabel = QLabel('Value: ')
                layout.addWidget(self.valueLabel, 2, 2)
                self.inputValue=QLineEdit('0')
                layout.addWidget(self.inputValue, 2, 3)

                self.attributeLabel = QLabel('Attribute: ')
                layout.addWidget(self.attributeLabel, 2, 4)
                self.inputAttribute=QLineEdit("i.e. 'Red' - leave blank if unkown")
                layout.addWidget(self.inputAttribute, 2, 5)

                self.cueLabel= QLabel('Cue: ')
                layout.addWidget(self.cueLabel, 4, 0)
                self.inputCue = QLineEdit('1')
                layout.addWidget(self.inputCue, 4, 1)

                self.fadeInLabel=QLabel('Fade Up')
                layout.addWidget(self.fadeInLabel, 3, 0)
                self.inputTimeIn=QLineEdit('3')
                layout.addWidget(self.inputTimeIn, 3, 1)
                self.fadeOutLabel=QLabel('Fade Down')
                layout.addWidget(self.fadeOutLabel, 3, 2)
                self.inputTimeOut=QLineEdit('3')
                layout.addWidget(self.inputTimeOut, 3, 3)

                updateButton = QPushButton('Transmit Signal', clicked = self.updateArray)
                layout.addWidget(updateButton, 2, 6)

                recordButton = QPushButton('Record Cue', clicked = self.saveCue)
                layout.addWidget(recordButton, 4, 2)

                goToCue = QPushButton('Go to Cue', clicked = self.loadCue)
                layout.addWidget(goToCue, 4, 3)

                playCue = QPushButton('Play Next Cue', clicked = self.playCues)
                layout.addWidget(playCue, 4, 4)

                deleteCue = QPushButton('Delete Cue', clicked = self.deleteCue)
                layout.addWidget(deleteCue, 5, 4)

                saveLoadButton = QPushButton('Save/Load to File', clicked = self.openSaveLoad)
                layout.addWidget(saveLoadButton, 5, 0)

                fixtureButton = QPushButton('View Patched Fixtures', clicked = self.openViewFix)
                layout.addWidget(fixtureButton, 4, 6)

                patchButton = QPushButton('Patch a fixture', clicked = self.openPatchFix)
                layout.addWidget(patchButton, 5, 6)

                colourButton = QPushButton('Colour Mixing for Fixtures', clicked = self.openColourFix)
                layout.addWidget(colourButton, 3, 6)

                panTiltButton = QPushButton('Control Moving Lights', clicked = self.openPanTiltFix)
                layout.addWidget(panTiltButton, 6, 6)

                layout.addWidget(self.errorMessage, 7, 0, 1, 7)

                debug = QPushButton('Open debug menu', clicked = self.openDebug)
                layout.addWidget(debug, 6, 0)
                #---------Setting up UI end---------

        ###Function Definitions
        def updateArray(self):#This updates the self.data attribute with new values at the channel indicated
                try:
                        channel = safeInt(self.inputChannel.text(), 'Channel')
                        value = safeInt(self.inputValue.text(), 'Target Value')
                        fixtureList = self.fixtureManager.getFixtureList()
                        if len(fixtureList) == 0:
                                raise PatchError('No fixtures patched')
                        if channel not in fixtureList.keys():
                                raise KeyError(f'There is no fixutre patched to channel {channel}')
                        if value > 255 or value < 0:
                               raise ValueError('The designated value must be between 0-255')
                        fixture = fixtureList[channel]
                        attribute = self.inputAttribute.text()
                        fixture.setAttribute(self.data, attribute, value)
                        sendOLA(self.data)
                        self.handleSuccess('Signal Transmitted')
                except (PatchError, KeyError, ValueError, IndexError) as e:
                        self.handleError(e)

        def saveCue(self):#This adds a cue to the cueManager. It will also increment the user input by one.
                #Need to create a new copy of data
                newData = self.data[:]
                try:
                        newCue = safeInt(self.inputCue.text(), 'Cue')
                        newIn = safeInt(self.inputTimeIn.text(), 'Fade in time')
                        newOut = safeInt(self.inputTimeOut.text(), 'Fade out time')
                        self.cueManager.addCue(newCue, newData, newIn, newOut)
                        #Creates UI for viewing this cue
                        cueList = self.cueManager.getCueList()
                        cueNums = []
                        for key in cueList.keys():
                               cueNums.append(key)
                        self.cueViewer.setRowCount(len(cueList))
                        cueNums.sort()
                        for row, cue in enumerate(cueNums):
                                self.cueViewer.setItem(row, 0, QTableWidgetItem(str(cue)))
                                self.cueViewer.setItem(row, 1, QTableWidgetItem('Click to edit Label'))
                        #Updates the input field
                        self.inputCue.setText(str(newCue + 1))
                        self.handleSuccess('Cue saved')
                except (ValueError, TypeError) as e:
                        self.handleError(e)

        def playCues(self):#Fades into next cue
                try:
                        currentCue = self.cueManager.getCurrentCue()
                        nextCue = self.cueManager.getNextCue()
                        nextCueNumber = self.cueManager.getPlaybackPointer()
                        #Updating UI
                        self.errorMessage.setText(f'Playing Cue {nextCueNumber}...')
                        self.errorMessage.setStyleSheet('color: yellow')
                        QApplication.processEvents()
                        #Call crossfade function
                        self.cueManager.crossFade(currentCue.frame, nextCue.frame, self.fadeRate, nextCue.fadeUp, currentCue.fadeDown)
                        self.data = nextCue.frame
                        sendOLA(self.data)
                        #Set text to display the current cue
                        self.inputCue.setText(str(nextCueNumber))
                        self.handleSuccess(f'Currently in Cue {nextCueNumber}')
                except IndexError as e:
                        self.handleError(e)

        def loadCue(self): #Changes output to selected cue. Also increments Pointer to select the next cue numerically
                try:
                        cueDict=self.cueManager.getCueList()
                        targetCue = safeInt(self.inputCue.text(),'Target Cue')
                        if targetCue not in cueDict.keys():
                               raise KeyError(f'Cue {targetCue} does not exist')
                        self.cueManager.setPlaybackCue(targetCue)
                        playback = cueDict[targetCue]
                        self.data = playback.frame
                        sendOLA(self.data)
                        self.handleSuccess('Loaded Cue')
                except (KeyError, ValueError) as e:
                       self.handleError(e)
        
        def deleteCue(self):#If targetCue = currentCue, set playbackpointer to currentCue position -1
                try:
                        cueList = self.cueManager.cueList
                        targetCue = safeInt(self.inputCue.text(), 'Target Cue')
                        currentCueID = self.cueManager.getPlaybackPointer()
                        if targetCue == currentCueID:
                                raise RuntimeError('Cannot delete a cue you are currently in')
                        cueList.pop(targetCue)
                        #Updating UI
                        cueList = self.cueManager.getCueList()
                        cueNums = []
                        for key in cueList.keys():
                               cueNums.append(key)
                        self.cueViewer.setRowCount(len(cueList))
                        cueNums.sort()
                        for row, cue in enumerate(cueNums):
                                self.cueViewer.setItem(row, 0, QTableWidgetItem(str(cue)))
                                self.cueViewer.setItem(row, 1, QTableWidgetItem('Click to edit Label'))
                except (RuntimeError) as e:
                        self.handleError(e)

        #---------Functions to open windows---------
        def openSaveLoad(self):
                self.fileWindow = SaveLoadWindow(self.cueManager, self.fixtureManager)
                self.fileWindow.show()

        def openPatchFix(self):
                self.patchWindow = PatchWindow(self.fixtureManager)
                self.patchWindow.show()

        def openViewFix(self):
                self.fixtureViewer = FixtureViewer(self.fixtureManager)
                self.fixtureViewer.show()

        def openColourFix(self):
                self.colourPicker = ColourPicker(self.data, self.fixtureManager)
                self.colourPicker.show()

        def openPanTiltFix(self):
                self.panTilt = PanTiltHandler(self.data, self.fixtureManager)
                self.panTilt.show()

        def openDebug(self):
                self.debug = DebugWindow(self.data, self.cueManager, self.fixtureManager)
                self.debug.show()
        #---------Functions to open windows end---------

class SaveLoadWindow(PIghtingWidget):
        def __init__(self, cueManager, fixtureManager):
                super().__init__()
                self.setWindowTitle('Save or Load to a File')
                ###Layout
                layout = QGridLayout()
                self.setLayout(layout)

                ###Controllers
                self.cueManager = cueManager
                self.fixtureManager = fixtureManager

                #---------Setting up UI---------
                self.nameLabel = QLabel('File Name: ')
                layout.addWidget(self.nameLabel, 0, 0)
                self.inputFileName = QLineEdit('example.pkl')
                layout.addWidget(self.inputFileName, 0, 1)

                saveButton = QPushButton('Save', clicked = self.saveToFile)
                layout.addWidget(saveButton, 1, 0)
                
                loadButton = QPushButton('Load', clicked = self.loadFromFile)
                layout.addWidget(loadButton, 1, 1)

                self.feedback= QLineEdit('')
                layout.addWidget(self.feedback, 2, 1)
                #---------Setting up UI end---------
        
        def saveToFile(self):
                cueList = self.cueManager.getCueList()
                fixtureList = self.fixtureManager.getFixtureList()
                saveDict = {
                        'cueList' : cueList,
                        'fixtureList' : fixtureList
                }
                with open(str(self.inputFileName.text()), 'ab') as file:
                        pickle.dump(obj = saveDict, file = file, protocol=pickle.HIGHEST_PROTOCOL, fix_imports=True)
                        self.feedback.setText(f"Show saved to {self.inputFileName.text()}")
        
        def loadFromFile(self):
                try:
                       with open(str(self.inputFileName.text()), 'rb') as file:
                                saveDict = pickle.load(file)
                                self.feedback.setText(f"Show {self.inputFileName.text()} loaded")
                                self.cueManager.cueList = saveDict['cueList']
                                self.fixtureManager.fixtureList = saveDict['fixtureList']
                except FileNotFoundError:
                        self.feedback.setText(f"File{self.inputFileName.text()} not found")

class PatchWindow(PIghtingWidget):
        def __init__(self, fixtureManager):
                super().__init__()
                self.setWindowTitle('Patch fixtures to channels')
                home = Path.home()
                if sys.platform == 'win32':
                        self.path = home / "AppData/Roaming/pighting"
                else:
                        self.path = home / ".local/share/pighting"
                pathStr = str(self.path)
                if os.path.exists(pathStr) is False:
                        os.mkdir(pathStr)
                self.DBPathStr = str(self.path / 'FixtureProfiles.db')

                ###Layout
                layout = QGridLayout()
                self.setLayout(layout)

                #---------Setting up UI---------
                self.tableLabel = QLabel("Fixtures- To patch a fixture, click on the correct fixture's name")
                layout.addWidget(self.tableLabel, 0, 0, 1, 2)

                self.fixtureManager = fixtureManager
                self.fixTable = QTableWidget()
                self.fixTable.setColumnCount(2)
                self.columns = ['Manufacturer' , 'Fixture - Mode']
                self.fixTable.setVerticalHeaderLabels(self.columns)
                layout.addWidget(self.fixTable, 1, 0, 1, 3)

                self.fetchData()

                self.searchQuery = QLineEdit('Search for Fixture')
                layout.addWidget(self.searchQuery, 2, 0)

                searchButton = QPushButton('Search', clicked = self.searchTable)
                layout.addWidget(searchButton, 2 , 1)

                updateButton = QPushButton('Update Fixture Profiles' , clicked = self.updateDB)
                layout.addWidget(updateButton, 4, 0)

                patchButton =QPushButton('Patch Selected Fixture', clicked = self.patchFixture2)
                layout.addWidget(patchButton, 4, 1)

                self.fixTable.cellClicked.connect(self.patchFixture)

                self.DMXAddress = QLineEdit('DMX Address')
                layout.addWidget(self.DMXAddress, 3 , 0)
                self.channel = QLineEdit('Channel')
                layout.addWidget(self.channel, 3 , 1)

                layout.addWidget(self.errorMessage, 5, 0, 1, 3)
                #---------Setting up UI end---------
                

        def fetchData(self):
                conn = sqlite3.connect(self.DBPathStr)
                cur = conn.cursor()     
                #Create DB if it doesn't exist
                cur.execute('''CREATE TABLE IF NOT EXISTS fixtures
                            (fixName TEXT , channels TEXT)''')
                cur.execute('''CREATE TABLE IF NOT EXISTS manufacturers
                            (man TEXT , fixName TEXT)''')       
                #Select all from the manufacturer db, then close the connection
                cur.execute('SELECT * FROM manufacturers')
                rows = cur.fetchall()
                conn.close()    
                #Insert data into table widget
                for row in rows:
                        index = rows.index(row)
                        self.fixTable.insertRow(index)
                        self.fixTable.setItem(index, 0, QTableWidgetItem(str(row[0])))
                        self.fixTable.setItem(index, 1, QTableWidgetItem(str(row[1])))

        def searchTable(self):
                #Clear the table
                self.fixTable.clearContents()

                #Initialise db connection
                conn = sqlite3.connect(self.DBPathStr)
                cur = conn.cursor()
                #Select fixture based on search field, using wildcard functionality of SQL to allow for spelling errors
                cur.execute('''
                            SELECT *
                            FROM manufacturers
                            WHERE man LIKE ?
                            OR fixName LIKE ?''', 
                            ('%' + str(self.searchQuery.text()) + '%' , '%' + str(self.searchQuery.text()) + '%')
                            )
                rows = cur.fetchall()
                conn.close()
                #Insert new data into table widget
                for row in rows:
                        index = rows.index(row)
                        self.fixTable.insertRow(index)
                        self.fixTable.setItem(index, 0, QTableWidgetItem(str(row[0])))
                        self.fixTable.setItem(index, 1, QTableWidgetItem(str(row[1])))

        def updateDB(self):
                #Create database
                conn = sqlite3.connect(self.DBPathStr)
                #Create a cursor
                cur = conn.cursor()
                #Create Fixtures and manufacturers table
                cur.execute('''CREATE TABLE IF NOT EXISTS fixtures
                                (fixName TEXT , channels TEXT)''')
                cur.execute('''CREATE TABLE IF NOT EXISTS manufacturers
                                (man TEXT , fixName TEXT)''')
                conn.commit()
                #URL for the GitHub API
                masterURL = "https://api.github.com/repos/OpenLightingProject/open-fixture-library/contents/fixtures"
                #List of folder names taken from the manufacturers.json file
                manURL = "https://raw.githubusercontent.com/OpenLightingProject/open-fixture-library/master/fixtures/manufacturers.json"
                manDF = pd.read_json(manURL)
                manDF = manDF.drop("$schema", axis='columns')
                folders = manDF.columns
                #Iterate through folders
                successCode = 200
                for folder in folders:
                        folderURL = f"https://api.github.com/repos/OpenLightingProject/open-fixture-library/contents/fixtures/{folder}"
                        #Fetch the contents of the folder using GitHub Requests API
                        response = requests.get(folderURL)
                        #Status code 200 = Request Succeeded
                        if response.status_code == successCode:
                                files = response.json()
                                #Filter out JSON files using suffix
                                jsonFiles = []
                                for file in files:
                                        if file['name'].endswith('.json'):
                                                jsonFiles.append(file)
                                for jsonFile in jsonFiles:
                                        #Construct the download URL
                                        downloadURL = jsonFile['download_url']
                                        #Fetch the JSON file using requests API
                                        response = requests.get(downloadURL)
                                        if response.status_code == successCode:
                                                #Converts into dictionary object for data processing
                                                fixDict = response.json()
                                                fixList = []
                                                #This skips over .JSON files in the GitHub which are not fixtures
                                                if 'redirectTo' in fixDict.keys():
                                                        break
                                                #Create a list of each mode
                                                if 'modes' in fixDict.keys():
                                                        for fixMode in fixDict['modes']:
                                                                fixEntry = (
                                                                    fixDict['name'] + ' - ' + fixMode['name'],
                                                                    fixMode['channels']
                                                                )
                                                                fixList.append(fixEntry)
                                                else:
                                                    fixList.append(fixDict['name'],fixDict['channels'])
                                                #Now insert into the fixture DB
                                                #Check DB for entries where the count of the fixName is 0
                                                for fixture , channels in fixList:
                                                        cur.execute('''SELECT COUNT (*)
                                                                FROM manufacturers
                                                                WHERE fixName = ?''',
                                                                (fixture,))
                                                        count = cur.fetchone()[0]
                                                        if count == 0:# Serialise the data into JSON so it can be stored in the table
                                                                channelsJSON = json.dumps(channels)
                                                                # Store it in the table
                                                                cur.execute('''INSERT INTO manufacturers 
                                                                    (man , fixName) 
                                                                    VALUES (? , ?)''',
                                                                    (folder , fixture)
                                                                    )
                                                        #Repeat process for fixture table
                                                        cur.execute('''SELECT COUNT (*)
                                                                FROM fixtures
                                                                WHERE fixName = ?''',
                                                                (fixture,))
                                                        count = cur.fetchone()[0]
                                                        if count == 0:
                                                                channelsJSON = json.dumps(channels)
                                                                cur.execute('''INSERT INTO fixtures 
                                                                    (fixName , channels) 
                                                                    VALUES (? , ?)''',
                                                                    (fixture , channelsJSON)
                                                                    )
                                                        self.handleSuccess(f'Fixture profile for {fixture} retrieved')
                                                conn.commit()
                                                self.handleSuccess('Fixture profiles updated')
                                        else:
                                                self.handleError(f"Failed to download {jsonFile['name']}")
                                        self.handleError('Fixtures Updated')
                        else:
                                self.handleError(f"Failed to fetch folder: {folder}")
                #Close db objects
                conn.close()
                self.fetchData()

        def patchFixture(self , row , column): #Creates a new Fixture object based on info in QTableWidgetItem
                try:
                        DMXAddress = safeInt(self.DMXAddress.text(), 'DMX Address')
                        channel = safeInt(self.channel.text(), 'Channel')
                        if DMXAddress > 512 or DMXAddress < 1: # Project currently only supports one DMX universe
                               raise ValueError('DMX Address must be between 1 and 512')
                        #This takes the name of the fixture from the table
                        fixName = self.fixTable.item(row, 1).text()
                        #This needs to be executed as an SQL query into the fixture table
                        conn = sqlite3.connect(self.DBPathStr)
                        cur = conn.cursor()
                        cur.execute('''
                                    SELECT *
                                    FROM fixtures
                                    WHERE fixName = ?''', 
                                    (fixName,)
                                    )
                        SQLFix = cur.fetchone()
                        #SQLFix[0] is the name of the fixture, that was serialised in updateDB. SQLFix[1] is the list of attributes serialised in updateDB.
                        newFixture = Fixture(SQLFix[0], json.loads(SQLFix[1]), DMXAddress, channel)
                        self.fixtureManager.addFixture(newFixture)
                        self.handleSuccess(f'A {SQLFix[0]} fixture has been patched at channel {self.channel.text()}')
                except (ValueError) as e:
                        self.handleError(e)
        
        def patchFixture2(self): #Users wanted a button to patch, functionality had to be added to acoomodate this
                try:
                        selectedCell = self.fixTable.selectedItems()
                        if len(selectedCell) > 1:
                                raise ValueError('Multiple fixtures selected')
                        if selectedCell:
                                selectedCell = selectedCell[0]
                                row = selectedCell.row()
                                column = selectedCell.column()
                                self.patchFixture(row, column)
                        else:
                                raise AttributeError('No fixture selected')
                
                except (ValueError) as e:
                        self.handleError(e)


        def handleError(self, error):
                self.errorMessage.setText(str(error))
                self.errorMessage.setStyleSheet('color: red')
        
        def handleSuccess(self, success):
                self.errorMessage.setText(success)
                self.errorMessage.setStyleSheet('color: green')


class FixtureViewer(PIghtingWidget):
        def __init__(self, fixtureManager):
                super().__init__()
                self.setWindowTitle('Display of All Fixtures')

                ###Controllers
                self.fixtureManager = fixtureManager

                ###Layout
                layout = QGridLayout()
                self.setLayout(layout)

                #---------Setting up UI---------
                self.tableLabel = QLabel("Fixtures")
                layout.addWidget(self.tableLabel, 0, 0)
                self.fixTable = QTableWidget()
                self.fixTable.setColumnCount(4)
                self.columns = ['Channel #' , 'Address','Fixture', 'Attributes']
                self.fixTable.setVerticalHeaderLabels(self.columns)
                layout.addWidget(self.fixTable, 1, 0)

                self.refresh = QPushButton('Refresh', clicked=self.fetchData)
                layout.addWidget(self.refresh, 2, 0)

                self.fetchData()
                #---------Setting up UI end---------

        def fetchData(self):
               fixtureList = self.fixtureManager.getFixtureList()
               self.fixTable.setRowCount(len(fixtureList))
               chanList = []
               for fixture in fixtureList:
                        chanList.append(fixture)
                        chanList.sort()
                #Updating UI
               for channel in chanList:
                        newFixture = fixtureList[channel]
                        self.fixTable.setItem(chanList.index(channel), 0, QTableWidgetItem(str(channel)))
                        self.fixTable.setItem(chanList.index(channel), 1, QTableWidgetItem(str(newFixture.address)))
                        self.fixTable.setItem(chanList.index(channel), 2, QTableWidgetItem(str(newFixture.type)))
                        self.fixTable.setItem(chanList.index(channel), 3, QTableWidgetItem(str(newFixture.attributes)))

class ColourPicker(PIghtingWidget):
        def __init__(self, data, fixtureManager):
                super().__init__()
                self.setWindowTitle('Colour Picker')

                self.data = data
                ###Controllers
                self.fixtureManager = fixtureManager

                ###Layout
                layout = QGridLayout()
                self.setLayout(layout)

                #---------Setting Up UI---------
                self.colourPicker = QColorDialog()
                layout.addWidget(self.colourPicker, 0, 0, 1, 4)
                self.colourPicker.setOption(QColorDialog.ColorDialogOption.NoButtons, True)

                chanLabel = QLabel('Channel Number:')
                layout.addWidget(chanLabel, 1, 0)
                self.channelSelect = QLineEdit()
                layout.addWidget(self.channelSelect, 1, 1)

                layout.addWidget(self.errorMessage, 2, 0, 1, 4)
                #---------Setting Up UI end---------
                #Connect currentColorChanged signal to colourOutput function
                self.colourPicker.currentColorChanged.connect(self.colourOutput)

        def colourOutput(self, color: QColor):
                try:
                        fixtureList = self.fixtureManager.getFixtureList()
                        channel = safeInt(self.channelSelect.text(), 'Channel')
                        lantern = fixtureList[channel]
                        #Accounting for variance in attribute name
                        if 'Red' in lantern.attributes:
                                AttributeRGBStr = ('Red', 'Green', 'Blue')
                        elif 'Red-All' in lantern.attributes:
                                AttributeRGBStr = ('Red-All', 'Green-All', 'Blue-All')
                        else:
                                raise AttributeError(
                                        f'Channel {channel} does not have RGB channels'
                                        )
                        #Get values from QColorDialog. First three values are RGB, rest are irrelevant.
                        colourRGB = color.getRgb()[:3]
                        colourValues = zip(AttributeRGBStr,colourRGB)
                        for colour, value in colourValues:
                                lantern.setAttribute(self.data, colour, value)
                        sendOLA(self.data)
                        self.handleSuccess('Colour updated')
                except (ValueError, AttributeError) as e:
                        self.handleError(e)

class PanTiltHandler(PIghtingWidget):
        def __init__(self, data, fixtureManager):
                super().__init__()
                self.setWindowTitle('ML Controller')

                self.data = data
                ###Controllers
                self.fixtureManager = fixtureManager

                ###Layout
                layout = QGridLayout()
                self.setLayout(layout)

                #---------Setting up UI---------
                self.panTable = QTableWidget()
                self.panTable.setColumnCount(4)
                self.columns = ['Channel #' , 'Fixture','Pan', 'Tilt']
                self.panTable.setVerticalHeaderLabels(self.columns)
                layout.addWidget(self.panTable, 0, 0, 1, 7)
                self.fetchData()

                self.upButton = QPushButton('Up')
                layout.addWidget(self.upButton, 1, 2)
                #Adding 4 timers that each time out ever 100ms, and connecting them to each button
                self.upTimer = QTimer()
                self.upTimer.setInterval(100)
                self.upTimer.timeout.connect(self.upFunction)
                self.upButton.pressed.connect(self.upTimer.start)
                self.upButton.released.connect(self.upTimer.stop)

                self.downButton = QPushButton('Down')
                layout.addWidget(self.downButton, 2, 2)
                self.downTimer = QTimer()
                self.downTimer.setInterval(100)
                self.downTimer.timeout.connect(self.downFunction)
                self.downButton.pressed.connect(self.downTimer.start)
                self.downButton.released.connect(self.downTimer.stop)

                self.leftButton = QPushButton('Left')
                layout.addWidget(self.leftButton, 2, 1)
                self.leftTimer = QTimer()
                self.leftTimer.setInterval(100)
                self.leftTimer.timeout.connect(self.leftFunction)
                self.leftButton.pressed.connect(self.leftTimer.start)
                self.leftButton.released.connect(self.leftTimer.stop)

                self.rightButton = QPushButton('Right')
                layout.addWidget(self.rightButton, 2, 3)
                self.rightTimer = QTimer()
                self.rightTimer.setInterval(100)
                self.rightTimer.timeout.connect(self.rightFunction)
                self.rightButton.pressed.connect(self.rightTimer.start)
                self.rightButton.released.connect(self.rightTimer.stop)
                
                self.chanLabel = QLabel('Channel:')
                layout.addWidget(self.chanLabel, 3, 0)
                self.chanInput = QLineEdit('0')
                layout.addWidget(self.chanInput, 3, 1)

                self.speedLabel = QLabel('MoveSpeed:')
                layout.addWidget(self.speedLabel, 3, 2)
                self.speedInput = QLineEdit('1')
                layout.addWidget(self.speedInput, 3, 3)

                self.invLabel = QLabel('Invert Tilt?')
                layout.addWidget(self.invLabel, 3, 4)
                self.invCheck = QCheckBox()
                layout.addWidget(self.invCheck, 3, 5)
                
                layout.addWidget(self.errorMessage, 4, 0, 1, 6)
                #---------Setting up UI end---------
        
        def fetchData(self):
                #Updates UI to fill table with Fixture with Pan and Tilt outputs
                fixtureList = self.fixtureManager.getFixtureList()
                self.panTable.setRowCount(len(fixtureList))
                chanList = []
                for fixture in fixtureList:
                        chanList.append(fixture)
                        chanList.sort()
                for fixture in fixtureList.values():
                        if 'Pan' in fixture.attributes or 'Tilt' in fixture.attributes:
                                channel = safeInt(fixture.channelNum, 'Channel')
                                panIndex = self.data[fixture.address - 1 + fixture.attributes.index('Pan')]
                                tiltIndex = self.data[fixture.address - 1 + fixture.attributes.index('Tilt')]
                                self.panTable.setItem(chanList.index(channel), 0, QTableWidgetItem(str(channel)))
                                self.panTable.setItem(chanList.index(channel), 1, QTableWidgetItem(str(fixture.type)))
                                self.panTable.setItem(chanList.index(channel), 2, QTableWidgetItem(str(panIndex)))
                                self.panTable.setItem(chanList.index(channel), 3, QTableWidgetItem(str(tiltIndex)))

        def upFunction(self):#Edits data slot while button is held
                try:
                        moveSpeed = safeInt(self.speedInput.text(), 'Movespeed')
                        fixtureList = self.fixtureManager.getFixtureList()
                        channel = safeInt(self.chanInput.text(), 'Channel')
                        chanList = [] 
                        for fixture in fixtureList:
                                chanList.append(fixture)
                                chanList.sort()
                        channel = safeInt(self.chanInput.text(), 'Channel')
                        if channel not in chanList:
                                raise KeyError(
                                        f'There is no fixutre patched to channel {channel}'
                                        )
                        fixture = fixtureList[channel]
                        if 'Tilt' not in fixture.attributes:
                                raise IndexError(
                                        f'Channel {channel} has no attribute Tilt'
                                        )
                        tiltSlotLoc = fixture.address+fixture.attributes.index('Tilt')-1
                        tiltSlot = self.data[tiltSlotLoc]
                        #Manipulate tiltSlot
                        if self.invCheck.isChecked() is False:
                                tiltSlot -= (1 * moveSpeed)
                        if self.invCheck.isChecked() is True:
                                tiltSlot += (1 * moveSpeed)
                        if tiltSlot < 0:
                                tiltSlot = 0
                        if tiltSlot > 255:
                                tiltSlot = 255
                        #Edit frame
                        self.data[tiltSlotLoc] = tiltSlot
                        #Update UI
                        self.panTable.setItem(
                                chanList.index(channel), 
                                3,#This is the column in the table that corresponds to tilt 
                                QTableWidgetItem(str(tiltSlot))
                                )
                        sendOLA(self.data)
                        self.handleSuccess('Tilt Updated')
                except (ValueError, KeyError, IndexError) as e:
                        self.handleError(e)
        
        def downFunction(self):#Same as upFunction, but reversed
                try:
                        moveSpeed = safeInt(self.speedInput.text(), 'Movespeed')
                        fixtureList = self.fixtureManager.getFixtureList()
                        chanList = []
                        for fixture in fixtureList:
                                chanList.append(fixture)
                                chanList.sort()
                        channel = safeInt(self.chanInput.text(), 'Channel')
                        if channel not in chanList:
                                raise KeyError(f'There is no fixutre patched to channel {channel}')
                        fixture = fixtureList[channel]
                        if 'Tilt' not in fixture.attributes:
                                raise IndexError(f'Channel {channel} has no attribute Tilt')
                        tiltSlotLoc = fixture.address+fixture.attributes.index('Tilt')-1
                        tiltSlot = self.data[tiltSlotLoc]
                        if self.invCheck.isChecked() is False:
                                tiltSlot += (1 * moveSpeed)
                        if self.invCheck.isChecked() is True:
                                tiltSlot -= (1 * moveSpeed)
                        if tiltSlot < 0:
                                tiltSlot = 0
                        if tiltSlot > 255:
                                tiltSlot = 255
                        self.data[tiltSlotLoc] = tiltSlot
                        self.panTable.setItem(chanList.index(channel), 3 #This is the column in the table that corresponds to tilt 
                                              , QTableWidgetItem(str(tiltSlot)))
                        sendOLA(self.data)
                        self.handleSuccess('Tilt Updated')
                except (ValueError, KeyError, IndexError) as e:
                        self.handleError(e)
        
        def leftFunction(self):#Same as upFunction, but edits Pan instead of tilt
                try:
                        moveSpeed = safeInt(self.speedInput.text(), 'Movespeed')
                        fixtureList = self.fixtureManager.getFixtureList()
                        chanList = []
                        for fixture in fixtureList:
                                chanList.append(fixture)
                                chanList.sort()
                        channel = safeInt(self.chanInput.text(), 'Channel')
                        if channel not in chanList:
                                raise KeyError(f'There is no fixutre patched to channel {channel}')
                        fixture = fixtureList[channel]
                        if 'Pan' not in fixture.attributes:
                                raise IndexError(f'Channel {channel} has no attribute Pan')
                        panSlotLoc = fixture.address+fixture.attributes.index('Pan')-1
                        panSlot = self.data[panSlotLoc]
                        panSlot -= (1 * moveSpeed)
                        if panSlot < 0:
                                panSlot = 0
                        if panSlot > 255:
                                panSlot = 255
                        self.data[panSlotLoc] = panSlot
                        self.panTable.setItem(chanList.index(channel), 2 #Column 2 is the column in the table that corresponds to pan
                                              , QTableWidgetItem(str(panSlot)))
                        sendOLA(self.data)
                        self.handleSuccess('Pan Updated')
                except (ValueError, KeyError, IndexError) as e:
                        self.handleError(e)
        
        def rightFunction(self):#Same as leftFunction, but increases Pan
                try:
                        moveSpeed = safeInt(self.speedInput.text(), 'Movespeed')
                        fixtureList = self.fixtureManager.getFixtureList()
                        chanList = []
                        for fixture in fixtureList:
                                chanList.append(fixture)
                                chanList.sort()
                        channel = safeInt(self.chanInput.text(), 'Channel')
                        if channel not in chanList:
                                raise KeyError(f'There is no fixutre patched to channel {channel}')
                        fixture = fixtureList[channel]
                        if 'Pan' not in fixture.attributes:
                                raise IndexError(f'Channel {channel} has no attribute Pan')
                        panSlotLoc = fixture.address+fixture.attributes.index('Pan')-1
                        panSlot = self.data[panSlotLoc]
                        panSlot += (1 * moveSpeed)
                        if panSlot < 0:
                                panSlot = 0
                        if panSlot > 255:
                                panSlot = 255
                        self.data[panSlotLoc] = panSlot
                        self.panTable.setItem(chanList.index(channel), 2 #Column 2 is the column in the table that corresponds to pan
                                              , QTableWidgetItem(str(panSlot)))
                        sendOLA(self.data)
                        self.handleSuccess('Pan Updated')
                except (ValueError, KeyError, IndexError) as e:
                        self.handleError(e)

class DebugWindow(PIghtingWidget):#Some functions were created in developing the software which are not part of system requiremnets, but may be useful anyway
        def __init__(self, data, cueManager, fixtureManager):
                super().__init__()
                self.setWindowTitle('Debug')

                self.data = data
                ###Controllers
                self.cueManager = cueManager
                self.fixtureManager = fixtureManager

                ###Layout
                layout = QGridLayout()
                self.setLayout(layout)

                #---------Setting up UI---------
                self.output = QTextEdit()
                layout.addWidget(self.output, 0, 0, 1, 5)

                slotLabel = QLabel('Slot')
                layout.addWidget(slotLabel, 1, 0)
                self.slotInput = QLineEdit()
                layout.addWidget(self.slotInput, 1, 1)

                valueLabel = QLabel('Value')
                layout.addWidget(valueLabel, 1, 2)
                self.valueInput = QLineEdit()
                layout.addWidget(self.valueInput, 1, 3)

                transmit = QPushButton('Transmit', clicked = self.updateArraySlot)
                layout.addWidget(transmit, 1, 4)

                viewCues = QPushButton('View Cues', clicked = self.viewCueList)
                layout.addWidget(viewCues, 2, 0)

                viewFixtures = QPushButton('View Fixtures', clicked = self.viewFixList)
                layout.addWidget(viewFixtures, 2, 4)
                #---------Setting up UI end---------

        
        def updateArraySlot(self):#This updates the self.data attribute with new values by slot, is mainly for debugging
                try:
                        channel = self.slotInput.text()
                        channel = safeInt(channel, 'Channel')
                        value = self.valueInput.text()
                        value = safeInt(value, 'Value')
                        self.data[channel] = value
                        sendOLA(self.data)
                        dataOut = str(self.data)
                        self.output.setText(dataOut)
                except (ValueError) as e:
                        self.output.setText(e)
        
        def viewCueList(self): 
                cueList = self.cueManager.getCueList()
                displayList = []
                for k,v in cueList.items():
                        displayList.append((k, v.frame))
                self.output.setText(str(displayList))

        def viewFixList(self):
                fixList = self.fixtureManager.getFixtureList()
                displayList = []
                for k,v in fixList.items():
                        displayList.append((k, v.type, v.address, v.channelNum, v.attributes))
                self.output.setText(str(displayList))
                
def DmxSent(status):#Adapted from code at https://github.com/OpenLightingProject/ola/blob/master/python/examples/ola_send_dmx.py
        if status.Succeeded():
                print('Success!')
        else:
                print('Error: %s' % status.message, file=sys.stderr)
        global wrapper
        if wrapper:
                wrapper.Stop()

def safeInt(target, context):
       try:
              return int(target)
       except (ValueError):
              raise ValueError(f'{context} must be an interger')
       
def sendOLA(frame): #Adapted from code at https://github.com/OpenLightingProject/ola/blob/master/python/examples/ola_send_dmx.py
        if sys.platform == 'win32': #OLA does not support Windows. Use this to print the outputs of frames if on Windows.
                print(frame)
        else:
                global client
                global wrapper
                client.SendDmx(1, frame, DmxSent)
                wrapper.Run()
if __name__ == '__main__':
        #Functional code for instantiating the Application
        app = QApplication(sys.argv)
        window = MainWindow()
        window.showMaximized()
        if sys.platform == 'linux':
                wrapper = ClientWrapper() 
                client = wrapper.Client() 
        sys.exit(app.exec())
