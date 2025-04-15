# Obscura: Privacy-Preserving Face Verification on Constrained Drone -- Proof-of-Concept Implementation


In the follwing, we provide the proof-of-concept (PoC) implementation of our [Obscura Protocol](#obscura-protocol-poc-implementation), where we provide instructions to compile and run the code.
The code is based from the following [repository CondEval](https://github.com/nann-cheng/CondEval).
## Obscura Protocol PoC Implementation

We describe the necessary steps and the requirements to run our protocol.

### Overview
The table below gives a small overview of the structure and necessary sub-folders of the `obscura` folder. For more details.

| Folder | Content |
| -----: | ------- |
| ```common``` | The `common` folder contains the constants.py which is necessary to change the path of the test data file and changing the IP address and the port. |
| ```data``` | The `data` folder contains all the data set files and the pickle files from the dealer (Trusted entity which genrates the shares).  |
| ```experiments``` | The `experiments` folder contains all the collected measurements and python script to reproduce our plots. |
| ```obscura-protocol``` | The `obscura-protocol` contains the dealer.py and obscura.py, where obscura.py contains the code for proof-of-concept.|


### Obscura Protocol PoC Instructions for Ubuntu 20.04 LTS

Here, we provide the instructions on install the necessary dependencies in Ubuntu 20.04 LTS

#### Install Dependencies

1. Update package list and install python3.11, pip:

   ```bash
   ## Update package list
   sudo apt update
   
   sudo apt install -y software-properties-common
   
   ## Adding Deadsnakes PPA and update package list again
   sudo add-apt-repository ppa:deadsnakes/ppa

   sudo apt update
   
   ## Install python3.11
   sudo apt install -y python3.11
   
   ## Install pip
   sudo apt install -y python3.11-distutils
   curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
   python3.11 get-pip.py
   
   ## Verify installation
   python3.11 --version
   pip3 --version
   ```

1. Install tno.mpc.communciation module:

   ```bash
   python -m pip install tno.mpc.communication
   ```


#### Prepare Obscura Protocol PoC

1. Clone this Git repository ([Obscura](https://github.com/Obscura.git)):

   ```bash
   git clone 'https://github.com/Obscura.git' ~/Obscura
   ```

1. Change to the Obscura Protocol PoC folder:

   ```bash
   cd ~/Obscura/obscura-protocol/
   ```


### Run the Obscura Protocol PoC

1. Compile:

   ```bash
   ## start dealer in the obscura-protocol folder if the data-folder is empty to generate new shares
   python3.9 dealer.py   

   ## run obscura 0 (drone)
   python3.9 obscura.py 0

   ## run obscura 1 (wireless device)
   python3.0 obscura.py 1
   ```

