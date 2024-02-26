# Bouncie Odometer Logger

This Python script integrates vehicle data from Bouncie with LubeLogger to update odometer readings automatically.

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package installer)
- Virtual environment (venv)

### Setting Up a Python Virtual Environment

1. Clone the repository to your local machine:

```bash
git clone https://github.com/mplawner/bouncie-lubelogger-sync.git
cd bouncie-lubelogger-sync
```

2. Create a virtual environment:

```bash
python3 -m venv venv
```

3. Activate the virtual environment:

- On Windows:

```bash
.\venv\Scripts\activate
```

- On macOS and Linux:

```bash
source venv/bin/activate
```

### Installing Dependencies

Install the required Python packages:

```bash
pip install requests
```

## Configuration

Create a `config.ini` file in the root directory of the project with the following structure:

```ini
[BouncieAPI]
client_id = YOUR_CLIENT_ID
client_secret = YOUR_CLIENT_SECRET
redirect_uri = http://localhost:8080 # Must match Server below
auth_url = https://auth.bouncie.com/oauth/authorize
endpoint_url = https://api.bouncie.dev/v1
token_url = https://auth.bouncie.com/oauth/token
auth_file = /path/to/bouncie-lubelogger-sync/auth_code.txt

[Server]
host = localhost
port = 8080

[LubeLoggerAPI]
host = LUBELOGGER_HOST_ADDRESS
port = LUBELOGGER_PORT

[LocationIQ]
endpoint_url = https://us1.locationiq.com/v1/reverse.php
api_key = YOUR_API_KEY

[Application]
target_dir = /path/to/output/csvfiles

[Logging]
log_file = /path/to/bouncie-lubelogger-sync/app.log
log_level = INFO
```

Replace `YOUR_CLIENT_ID`, `YOUR_CLIENT_SECRET`, `YOUR_REDIRECT_URI`, `LUBELOGGER_HOST_ADDRESS`, and `LUBELOGGER_PORT` with your actual credentials and settings.

## Running the Script

To run the script, ensure your virtual environment is activated, then execute:

```bash
python bouncie-odo.py --config config.ini
```

## Setting Up a Cron Job

To run this script at regular intervals using cron:

1. Open your crontab file:

```bash
crontab -e
```

2. Add a line to schedule the script. For example, to run it every day at midnight:

```cron
0 0 * * * /path/to/your/venv/bin/python /path/to/bouncie-odo.py --config /path/to/config.ini >> /path/to/logfile.log 2>&1
```

Replace `/path/to/your/venv/bin/python` with the actual path to the Python executable in your virtual environment, and `/path/to/bouncie-odo.py` with the actual path to your `bouncie-odo.py` script.

3. Save and close the crontab.
