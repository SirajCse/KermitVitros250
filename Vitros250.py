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
import tkinter as tk
from tkinter import messagebox


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


API_URL = config.get("SETTINGS", "API_URL", fallback="https://www.htncr.org/ajax/set-hl7")
GET_URL = config.get("SETTINGS", "GET_URL", fallback="https://www.htncr.org/ajax/set-hl7-barcode")
API_KEY = config.get("SETTINGS", "API_KEY", fallback="66ffe8a2-b1b0-800a-802b-ec397f1bcec8")
DEVICE_MODEL = config.get("SETTINGS", "DEVICE_MODEL", fallback="vitros")

# Parse JSON
with open('config.json', 'r') as file:
    test_specific_mappings = json.load(file)


# Setup logging
logging.basicConfig(
    filename="readme.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# Queue for storing unsent data
unsent_queue = Queue()

def on_close():
    # Show confirmation dialog
    if messagebox.askyesno("Confirm Exit", "Are you sure you want to close?"):
        root.destroy()  # Close the window
    else:
        pass  # Do nothing and return to the application


def format_value(value):
    return f"{round(value, 2):.2f}"

def format_value_1f(value):
    return f"{round(value, 2):.1f}"

def format_int_value(value):
    return int(value) if value.is_integer() else value


def get_test_id(barcode):
    """Sends the parsed JSON to the API endpoint and retrieves the test IDs."""
    try:
        headers = {"Content-Type": "application/json"}
        payload = {
            "api": API_KEY,
            "barcode": barcode,
        }

        # Send POST request
        response = requests.post(GET_URL, json=payload, headers=headers, timeout=10)

        # Check for successful response
        if response.status_code == 200:
            try:
                response_json = response.json()

                # Check if 'data' exists in the response
                if "data" in response_json:
                    try:
                        test_ids = {
                            entry["test_id"]: {
                                "test_name": entry["test_name"],
                                "patient_name": entry["patient_name"]
                            }
                            for entry in response_json["data"]
                        }
                        return test_ids
#                       return {test["test_id"]: test["test_name"] for test in response_json["data"]}
                    except ValueError as e:
                        return []
                else:
                    logging.error("No Data get from server.")
                    return []
            except ValueError as e:
                logging.error(f"Error parsing JSON response: {e}")
                return []

        else:
            logging.error(f"Barcode API error: {response.status_code} - {response.text}")
            return []

    except requests.RequestException as e:
        logging.error(f"Request exception while getting test ID: {e}")
        return []


def handle_test_logic(test_name, suffix, test_ids, barcode, value, test_unit):
    data = []
    not_found = True

    if test_name in test_specific_mappings:
        if test_name == "GLU":
            suffix_normalized = suffix.lower()
            suffix_entries = test_specific_mappings["GLU"].get(suffix_normalized, test_specific_mappings["GLU"]["default"])
        else:
            suffix_entries = test_specific_mappings.get(test_name, [])

        for entry in suffix_entries:
            # Handle test_ids properly

            if isinstance(test_ids, dict):
                test_data = test_ids.get(entry["test_id"], {})
                test_name = test_data.get("test_name", '') + " " + test_name
                patient_name = test_data.get("patient_name", "Unknown Patient")
                try:
                    if test_data:
                        not_found = False
                        data.append({
                            "barcode": barcode,
                            "id": entry["id"],
                            "test_id": entry["test_id"],
                            "name": test_name,
                            "patient_name": patient_name,
                            "value": value,
                            "unit": test_unit,
                        })

                except KeyError as e:
                    logging.warning(f"KeyError in entry processing: {e}, entry: {entry}")
                except IndexError as e:
                    logging.warning(f"IndexError in entry processing: {e}, entry: {entry}")

        if not_found:
            not_found = False
            data.append({
                "barcode": barcode,
                "id": 0,
                "test_id": 0,
                "name": test_name,
                "patient_name": "Unknown Patient",
                "value": value,
                "unit": test_unit,
            })
    else:
        logging.warning(f"Test name {test_name} not in test_specific_mappings.")

    return data


def parse_message(message):
    """Parse the serial message into structured data."""
    lines = message.strip().split("\n")
    barcode = None
    date = None
    data = []
    test_ids = []
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

                test_ids = get_test_id(barcode)

                if not test_ids:
                    test_ids = []

            elif re.match(r"!\d{3}f", line):
                # Use slicing or regex to extract data
                test_name, test_value, test_unit = line[5:9].strip(), line[9:16].strip(), line[16:25].strip()

                if not (test_name and test_value and test_unit):
                    continue

                value = float(re.sub(r"[^\d.]", "", test_value.strip()))  # Strip non-numeric chars and trim whitespace

                if test_name in ["CREA", "ALB"]:
                    value = format_value(value)
                elif test_name in ["ECO2"]:
                    value = format_value_1f(value)
                #else    
                #    value = format_int_value(value)

                data.extend(handle_test_logic(test_name, suffix, test_ids, barcode, value, test_unit))


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
            formatted_data.append(item)

        payload = {
            "api": API_KEY,
            "barcode": formatted_data[0]["barcode"],
            "device_model": DEVICE_MODEL,
            "date": datetime.now().strftime("%Y%m%d%H%M%S"),
            "data": json.dumps(formatted_data),
        }

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


def format_row(item):
    """Format a row with fixed-width formatting, ensuring padding with spaces to the right if necessary."""
    return [
        str(item.get('patient_name', ' ')).ljust(20),  # Barcode (right-padded to 10 chars)
        str(item.get('barcode', ' ')).ljust(10),  # Barcode (right-padded to 10 chars)
        str(item.get('name', ' ')).ljust(25),     # Test Name (right-padded to 15 chars)
        str(item.get('value', ' ')).ljust(10),    # Value (right-padded to 10 chars)
        str(item.get('unit', ' ')).ljust(10),     # Unit (right-padded to 10 chars)
        str(item.get('status', ' ')).ljust(10),   # Status (right-padded to 10 chars)
    ]


def process_buffer(buffer, remaining_packets=None):
    """
    Processes a buffer line by line to extract complete packets
    starting with '!NNNa' and ending with '!NNNh'.
    Uses `remaining_packets` to handle partial data across calls.
    """
    if remaining_packets is None:  # Initialize if not provided
        remaining_packets = ''
        packet = ''  # Start fresh
    else:
        packet = remaining_packets  # Continue from the leftover data

    lines = buffer.splitlines()  # Split the new buffer into lines
    complete_packets = []  # To store completed packets

    for line in lines:
        logging.warning(f"Data line: {line}")
        logging.warning(f"Data Packet: {packet}")
        if re.match(r"!\d{3}a", line):  # Start of a new packet
            if packet:  # If there's an unfinished packet, log it
                logging.warning(f"Discarding incomplete packet: {packet}")
            packet = line  # Start a new packet
        elif re.match(r"!\d{3}h", line):  # End of a packet
            if packet:  # If a packet is in progress
                packet += f"\n{line}"
                complete_packets.append(packet)  # Save the completed packet
                packet = ''  # Reset for the next packet
            else:
                logging.warning(f"End of packet found without a start: {line}")
        elif re.match(r"!\d{3}[a-z]", line):  # Valid line within a packet
            if packet:
                packet += f"\n{line}"
            else:
                logging.warning(f"Data line outside of a packet: {line}")
        else:
            packet += line

    # Store any remaining incomplete packet in `remaining_packets`
    remaining_packets = packet if packet else ''
    logging.info(f"Complete Packets Data: {complete_packets}")
    logging.info(f"Remaining Packets Data: {remaining_packets}")
    return complete_packets, remaining_packets


def main():
    while True:
        try:
            # Alert if configuration is invalid
            if not SERIAL_PORT or not BAUD_RATE:
                print("Error: Serial port configuration is missing or invalid. Please check the settings.", flush=True)
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

            print(f"Developed by Siraj-Ud-Doulla \nCEO & Founder of Bit Dream IT.", flush=True)
#              \nPress Ctrl+C to stop

            headers_displayed = False
            remaining_packets = ''

            while True:
                try:
                    # Read from Serial
                    if receiver.in_waiting > 0:
                        raw_data = receiver.read(receiver.in_waiting).decode("utf-8").strip()
                        logging.info(f"Raw Data: {raw_data}")
                        complete_packets, remaining_packets = process_buffer(raw_data,remaining_packets)
                        

                        if not complete_packets:
                            continue  # Skip if no complete packets

                        for packet in complete_packets:
                            parsed_data = parse_message(packet)

                            # Send parsed data to API
                            if parsed_data and len(parsed_data) > 0:
                                if send_to_api(parsed_data):
                                    logging.info(f"Parsed Data: {parsed_data}")
                                    pass
                                else:
                                    unsent_queue.put(parsed_data)
                            else:
                                continue

                            # Prepare and display table
                            table_data = [format_row(item) for item in parsed_data]

                            if table_data:
                                if not headers_displayed:
                                    print(tabulate(
                                        table_data,
                                        headers=[ "Patient Name        ","Barcode   ", "Test Name                ", "Value     ", "Unit      ", "Status    "],
                                        tablefmt="pretty",
                                        stralign="center"
                                    ), flush=True)
                                    headers_displayed = True
                                else:
                                    print(tabulate(table_data,
                                        headers=[ "--------------------","----------", "-------------------------", "----------", "----------", "----------"],
                                        tablefmt="pretty", stralign="center"), flush=True)

                    # Process unsent queue
                    process_queue()

                except Exception as e:
                    logging.error(f"Error during data transfer: {e}")
                    break

        except serial.SerialException as e:
            print(f"Error: Could not open serial port {SERIAL_PORT}. Retrying in {RECONNECT_DELAY} seconds...",flush=True)
            logging.error(f"Serial connection error: {e}. Retrying...")
            time.sleep(RECONNECT_DELAY)
        finally:
            try:
                receiver.close()
            except:
                pass

if __name__ == "__main__":
    main()

