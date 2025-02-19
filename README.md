# PIghting-Controller
DMX512 Lighting Control Software for Raspberry Pi - Designed and Tested using the DMX Interface for Raspberry Pi from BitWizard (https://www.bitwizard.nl/shop/DMX-interface-for-Raspberry-pi)

###Intro###

The system has 2 different versions of implementation as follows:
1) Linux with OLA without intent to broadcast signal
2) Full implementation on specified hardware

Crucially, OLA cannot be installed using pip install. It has to be installed in accordance with Implementation 1 or 2. 

###Implementation 1###

1) Run: 
	sudo nano /etc/apt/sources.list 
2) Add to file:
	deb   http://apt.openlighting.org/debian  squeeze main
3) Run: 
	sudo apt-get update
	sudo apt-get install ola
	sudo apt-get install ola-python
4) Once installed, access the OLA interface at localhost:9090/ola.html
5) Click ‘home’
6) Click ‘add universe’
7) In universe ID, input 1. For universe name, describe what type of universe is actually going to be used. Select ‘Dummy Device’. This will let you visualise the DMX universe through OLA even if no network is connected
8) Go to All Implementations

###Implementation 2###
There are a few tutorials online, but none of them work if followed independently. These instructions contain the full instructions needed to install OLA, and how to get it configured for the Pighting Controller. These instructions have been compiled from the following sources:
https://bitwizard.nl/wiki/index.php/Dmx_interface_for_raspberry_pi#bullseye
https://www.openlighting.org/ola/linuxinstall/

This method has been tested and is working on 2024-07-04 RasPiOS modification of Debian Bookworm

Before OLA is installed, some things must be configured on the Raspberry Pi first.
1. Run the command ‘sudo raspi-config’ in the terminal
2. Go to option 3, interface options
3. Go to option 6, serial interface
4. Select no to both prompts
5. The serial interface is now disabled, freeing up the hardware to be used by OLA
• This should be enough to disable serial on the Raspberry Pi entirely, if not continue following from step 6. Otherwise skip to the next numbered list
6. Run the command ‘sudo disable serial-getty@ttyAMA0.service’
7. Run the command ‘sudo nano / boot/firware/cmdline.txt’
8. Look for an entry starting console=ttyAMA or console=serial0. Delete the whole console= entry without editing the rest of the line.

Additional configuration.
1. Add the line init_uart_clock=16000000 to BOTH /boot/firware/config.txt and / boot/firware/cmdline.txt, as install instructions are ambiguous as to which file it has to be in
2. Disable Bluetooth by adding dtoverlay=disable-bt to /boot/firware/config.txt
3. Add the line below to /etc/rc.local that modifies the GPIO pins, otherwise this will have to be done manually
	• sudo pinctrl set 18 op dh

Now OLA must be compiled from source.
1. Open terminal and run ‘sudo nano /etc/apt/sources.list’
2. Delete the ‘#’ character before deb-src. Save and close the file.
3. Now run ‘git clone https://github.com/OpenLightingProject/ola.git’ to obtain the sources for install
4. Add OLA as a user to the system by running the command ‘sudo adduser --system olad’
5. The build is configured and installed with:
	cd ola 
 	autoreconf -i
 	./configure --prefix=/usr
	--enable-python-libs
 	make -j4 
 	sudo make install
•You may have to run sudo apt-get update first
6. This will take about 15 minutes to compile
7. Run the command ‘sudo adduser olad tty’ to allow it to write to the device 

Some OLA settings must be changed
1. Locate the file named ‘ola-uartdmx.conf’ within the OLA directory.
2. Edit the file with the following:
	/dev/ttyAMA0-break = 100
	/dev/ttyAMA0-malf = 24000
	device = /dev/ttyAMA0
	enabled = true
3. Open OLA at localhost:9090 in the web browser.
4. Click stop OLA
5. Open terminal
6. Run ‘olad -l 3’ to ensure that when OLA restarts, the UARTDMX plug in is running correctly

Now, OLA must be used to create a universe
1. Access the OLA interface at localhost:9090/ola.html
2. Click ‘home’
3. Click ‘add universe’
4. In universe ID, input 1. For universe name, describe what type of universe is actually going to be used
	• If you are following these instructions recreationally, and do not have a raspberry pi, select ‘Dummy Device’. This will let you visualise the DMX universe through 	OLA even if no network is connected
	• If you have a raspberry pi with the DMX shield, select ‘UART Native DMX’. If it is not on the list, go back to home and click ‘Reload Plugins’. If it is still not 	on the list, ensure that OLA has been installed correctly in accordance with these instructions.

###All Implementations###
1) Extract the contents of the PIghting Code folder
2) Open your IDE of choice*
3) In the terminal of the IDE, navigate to the extracted PIghting Code folder
4) Create a new virtual environment by running the following in the terminal**:
	python3 -m venv venv
5) Activate the venv:
On Linux : 
	source venv/bin/activate
On Windows: 
	.\venv\Scripts\activate
6) Install the requisites:
	pip install -r requirements.txt
7) If you wish to use the provided FixtureProfiles DB, instead of compiling from scratch use file explorer to move the FixtureProfiles.db file to:
	On Linux : 
		/home/YOURACCOUNT/.local/share/pighting
	On Windows:
		C:\Users\YOURACCOUNT\AppData\Roaming\pighting
8) Run the PIghting Final.py file
	
*tested with VSCode. There is a known issue where a syntax error is raised before the import statements begin. As far as I can tell, this is an issue with VSCode and can be resolved by restarting the software.
**Other methods of creating a virtual environment also work.
