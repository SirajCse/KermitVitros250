# Design for Vitros 250 Upload Only Mode
# Developed by Siraj-Ud-Doulla CEO & Founder of Bit Dream IT

import serial
import time
import logging
import configparser
import os
import re
import json
import requests
from queue import Queue
from datetime import datetime
import signal
from tabulate import tabulate

# Read configuration
CONFIG_FILE = "config.ini"
config = configparser.ConfigParser()

# Ensure config file exists
if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"Configuration file '{CONFIG_FILE}' not found.")

config.read(CONFIG_FILE)

# Extract settings
SERIAL_PORT = config.get("SETTINGS", "SERIAL_PORT", fallback="COM3")
BAUD_RATE = config.getint("SETTINGS", "BAUD_RATE", fallback=9600)
PARITY = config.getint("SETTINGS", "PARITY", fallback=serial.PARITY_NONE)
STOPBITS = config.getint("SETTINGS", "STOPBITS", fallback=serial.STOPBITS_ONE)
SIZE = config.getint("SETTINGS", "SIZE", fallback=serial.EIGHTBITS)
TIMEOUT = config.getint("SETTINGS", "TIMEOUT", fallback=0)
RECONNECT_DELAY = config.getint("SETTINGS", "RECONNECT_DELAY", fallback=5)


API_URL = config.get("SETTINGS", "API_URL", fallback="http://www.htncr.com/ajax/set-hl7")
API_KEY = config.get("SETTINGS", "API_KEY", fallback="66ffe8a2-b1b0-800a-802b-ec397f1bcec8")
DEVICE_MODEL = config.get("SETTINGS", "DEVICE_MODEL", fallback="vitros")

# Setup logging
logging.basicConfig(
    filename="readme.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# Queue for storing unsent data
unsent_queue = Queue()

# ID and Test mappings

id_mapping = {
    'GLU': 2, 'CREA': 75,  'ALTV': 8, 'ALB': 166, 'CHOL': 174, 'TRIG': 180, 'HDLC': 176, 'CRP': 141, 'Fe': 214, 'ECO2': 488, 'TIBC': 218
}

test_mapping = {
    'GLU': 1, 'CREA': 74,  'ALTV': 7, 'ALB': 165, 'CHOL': 173, 'TRIG': 179, 'HDLC': 175, 'CRP': 140, 'Fe': 213, 'ECO2': 211, 'TIBC': 217
}

def format_value(value):
    """Apply any custom formatting logic for value."""
    # This function can be expanded with specific rules for formatting
    return round(value, 2)

def format_int_value(value):
    """Format integer values (if applicable)."""
    return int(value) if value.is_integer() else value


def parse_message(message):
    """Parse the serial message into structured data."""
    lines = message.strip().split("\n")
    barcode = None
    data = []
    suffix = ''

    for line in lines:
        try:
            if line.startswith("!000a"):
                # Extract  165749241204429-RCS timestamp and barcode
                time = line[17:23].strip()
                date = f"{line[23:29].strip()}{time}"
                barcode = line[29:44].strip()
                if barcode:
                    parts = barcode.split('-')
                    suffix = parts.pop() if len(parts) > 1 else ''
                    barcode = '-'.join(parts)
                else:
                    suffix = ''

            elif re.match(r"!\d{3}f", line):
                # Use slicing or regex to extract data
                test_name, test_value, test_unit = line[5:9].strip(), line[9:16].strip(), line[16:25].strip()
                
                if not (test_name and test_value and test_unit):
                    logging.warning(f"Skipping malformed line: {line}")
                    continue

                value = float(re.sub(r"[^\d.]", "", test_value.strip()))  # Strip non-numeric chars and trim whitespace

                id_value = id_mapping.get(test_name, None)
                test_id = test_mapping.get(test_name, None)

                formatted_data = {
                    "date": date,
                    "barcode": barcode,
                    "id": id_value,
                    "test_id": test_id,
                    "name": test_name,
                    "value": value,
                    "unit": test_unit,
                }

                if test_name in ["CREA", "ALB"]:
                    formatted_data["value"] = format_value(value)
                
                if test_name == "GLU":

                    if suffix == 'f':
                        data.extend([
                            {"date": date, "barcode": barcode, "id": 2, "test_id": 1, "name": test_name, "value": value, "unit": test_unit},
                            {"date": date, "barcode": barcode, "id": 62, "test_id": 61, "name": test_name, "value": value, "unit": test_unit},
                            {"date": date, "barcode": barcode, "id": 153, "test_id": 152, "name": test_name, "value": value, "unit": test_unit},
                        ])
                    elif suffix == '1h':
                        data.append({"date": date, "barcode": barcode, "id": 148, "test_id": 61, "name": test_name, "value": value, "unit": test_unit})
                    elif suffix == '2h':
                        data.extend([
                            {"date": date, "barcode": barcode, "id": 60, "test_id": 59, "name": test_name, "value": value, "unit": test_unit},
                            {"date": date, "barcode": barcode, "id": 1206, "test_id": 1205, "name": test_name, "value": value, "unit": test_unit},
                            {"date": date, "barcode": barcode, "id": 150, "test_id": 61, "name": test_name, "value": value, "unit": test_unit},
                            {"date": date, "barcode": barcode, "id": 155, "test_id": 152, "name": test_name, "value": value, "unit": test_unit},
                        ])
                    elif suffix == 'r':
                        data.append({"id": 4, "test_id": 3, "name": test_name, "value": value, "unit": test_unit})
                    else:
                        data.extend([
                            {"date": date, "barcode": barcode, "id": 2, "test_id": 1, "name": test_name, "value": value, "unit": test_unit},
                            {"date": date, "barcode": barcode, "id": 4, "test_id": 3, "name": test_name, "value": value, "unit": test_unit},
                        ])


                if test_name == "HDLC":
                    data.extend([
                        {"date": date, "barcode": barcode, "id": 130, "test_id": 65, "name": test_name, "value": value, "unit": test_unit},
                        {"date": date, "barcode": barcode, "id": 145, "test_id": 142, "name": test_name, "value": value, "unit": test_unit},
                    ])
                elif test_name == "CHOL":
                     data.extend([
                         {"date": date, "barcode": barcode, "id": 66, "test_id": 65, "name": test_name, "value": value, "unit": test_unit},
                         {"date": date, "barcode": barcode, "id": 144, "test_id": 142, "name": test_name, "value": value, "unit": test_unit},
                     ])
                elif test_name == "TRIG":
                    data.extend([
                        {"date": date, "barcode": barcode, "id": 129, "test_id": 65, "name": test_name, "value": value, "unit": test_unit},
                        {"date": date, "barcode": barcode, "id": 145, "test_id": 142, "name": test_name, "value": value, "unit": test_unit},
                    ])

                
                data.append(formatted_data)


            elif line.startswith("!002h"):
                break

        except (IndexError, ValueError, KeyError) as e:
            logging.warning(f"Error processing line: {line}. Error: {e}")
            continue

    return data


def send_to_api(parsed_data):
    """Sends the parsed JSON to the API endpoint."""
    try:
        headers = {"Content-Type": "application/json"}
        formatted_data = []
        for item in parsed_data:
            item["test_id"] = test_mapping.get(item["name"], "")
            formatted_data.append(item)


        payload = {
            "api": API_KEY,
            "barcode": formatted_data[0]["barcode"],
            "device_model": DEVICE_MODEL,
            "date": datetime.now().strftime("%Y%m%d%H%M%S"),
            "data": json.dumps(formatted_data),
        }

        logging.debug(f"Formatted Data: {payload}")

        response = requests.post(API_URL, json=payload, headers=headers, timeout=10)

        if response.status_code == 200:
            for item in parsed_data:
                item["status"] = "success"
            return True
        else:
            logging.error(f"API error: {response.status_code} - {response.note}")
            # Update status to failed if API request fails
            for item in parsed_data:
                item["status"] = "failed"
            return False
            
    except requests.RequestException as e:
        logging.error(f"Request exception: {e}")
        # Update status to failed if an exception occurs
        for item in parsed_data:
            item["status"] = "failed"
        return False


def process_queue():
    """Processes the queue and retries sending unsent data to the API."""
    backoff = 1  # Start with a 1-second delay
    while not unsent_queue.empty():
        parsed_data = unsent_queue.queue[0]  # Peek at the first item
        logging.info("Retrying to send queued data...")

        if send_to_api(parsed_data):
            unsent_queue.get()  # Remove item from the queue if successful
            backoff = 1  # Reset backoff on success
        else:
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)  # Cap backoff at 60 seconds
            logging.warning("Retrying after backoff...")


def signal_handler(sig, frame):
    exit(0)

signal.signal(signal.SIGINT, signal_handler)

def process_buffer(buffer):
    """
    Processes a buffer line by line to extract complete packets
    starting with '!NNNa' and ending with '!NNNh'.
    """
    lines = buffer.splitlines()  # Split buffer into lines
    packet = []  # Temporary storage for the current packet
    complete_packets = []  # Store complete packets

    for line in lines:
        if re.match("!\\d{3}a", line):  # Start of a new packet
            if packet:  # If there was an unfinished packet, discard it
                logging.warning(f"Discarding incomplete packet: {packet}")
            packet = [line]  # Start a new packet

        elif re.match("!\\d{3}h", line):  # End of a packet
            if packet:  # If a packet is in progress
                packet.append(line)
                complete_packets.append("\n".join(packet))  # Save the completed packet
                packet = []  # Reset for the next packet
            else:
                logging.warning(f"End of packet found without a start: {line}")

        elif re.match("!\\d{3}[a-z]", line):  # Valid line within a packet
            if packet:
                packet.append(line)
            else:
                logging.warning(f"Data line outside of a packet: {line}")


    return complete_packets, "\n".join(packet) if packet else ""  # Return complete packets and remaining buffer


def format_row(item):
    """Format a row with fixed-width formatting, ensuring padding with spaces to the right if necessary."""
    return [
        str(item.get('date', ' ')).ljust(14),     # Date (right-padded to 14 chars)
        str(item.get('barcode', ' ')).ljust(10),  # Barcode (right-padded to 10 chars)
        str(item.get('name', ' ')).ljust(15),     # Test Name (right-padded to 15 chars)
        str(item.get('value', ' ')).ljust(10),    # Value (right-padded to 10 chars)
        str(item.get('unit', ' ')).ljust(10),     # Unit (right-padded to 10 chars)
        str(item.get('status', ' ')).ljust(10),   # Status (right-padded to 10 chars)
    ]



def testing():
    """Test the parsing and data sending process."""
    print("Starting the Serial-to-API script...")

    # Process data
    complete_packets, remaining_buffer = process_buffer(mock_serial_data)

    if not complete_packets:
        print("No complete packets parsed. Please check the mock data format.")
        return

    headers_displayed = False  # Track whether headers have been printed

    for packet in complete_packets:
        parsed_data = parse_message(packet)

        # Send parsed data to API
        if parsed_data and send_to_api(parsed_data):
            pass  # Do nothing for successful API calls
        else:
            logging.error("Failed to send data to the API.")


        # Prepare data for table display
        table_data = [format_row(item) for item in parsed_data]

        # Display the table with a fixed width for the columns
        if table_data:
            if not headers_displayed:
                print(tabulate(
                    table_data,
                    headers=["Barcode", "Date", "Test Name", "Value", "Unit", "Status"],
                    tablefmt="grid",
                    stralign="center"
                ))
                headers_displayed = True
            else:
                print(tabulate(table_data, tablefmt="grid", stralign="center"))

def main():
    while True:
        try:
            # Alert if configuration is invalid
            if not SERIAL_PORT or not BAUD_RATE:
                print("Error: Serial port configuration is missing or invalid. Please check the settings.")
                return

            # Attempt to connect to serial port
            receiver = serial.Serial(
                port=SERIAL_PORT,
                baudrate=BAUD_RATE,
                bytesize=SIZE,
                parity=PARITY,
                stopbits=STOPBITS,
                timeout=TIMEOUT
            )
            print(f"Listening on {receiver.port}... (Press Ctrl+C to stop)", flush=True)

            headers_displayed = False  # Track whether headers have been printed
            while True:
                try:
                    # Read from Serial
                    if receiver.in_waiting > 0:
                        raw_data = receiver.read(receiver.in_waiting).decode("utf-8").strip()
                        complete_packets, remaining_buffer = process_buffer(raw_data)

                        if not complete_packets:
                            continue  # Skip if no complete packets

                        for packet in complete_packets:
                            parsed_data = parse_message(packet)

                            # Send parsed data to API
                            if parsed_data and send_to_api(parsed_data):
                                pass
                            else:
                                logging.error("Failed to send data to the API.")
                                unsent_queue.put(parsed_data)

                            # Prepare and display table
                            table_data = [format_row(item) for item in parsed_data]
                            if table_data:
                                if not headers_displayed:
                                    print(tabulate(
                                        table_data,
                                        headers=["Date", "Barcode", "Test Name", "Value", "Unit", "Status"],
                                        tablefmt="grid",
                                        stralign="center"
                                    ), flush=True)
                                    headers_displayed = True
                                else:
                                    print(tabulate(table_data, tablefmt="grid", stralign="center"), flush=True)

                    # Process unsent queue
                    process_queue()

                except Exception as e:
                    logging.error(f"Error during data transfer: {e}")
                    break

        except serial.SerialException as e:
            print(f"Error: Could not open serial port {SERIAL_PORT}. Retrying in {RECONNECT_DELAY} seconds...")
            logging.error(f"Serial connection error: {e}. Retrying...")
            time.sleep(RECONNECT_DELAY)
        finally:
            try:
                receiver.close()
            except:
                pass

if __name__ == "__main__":
    main()

