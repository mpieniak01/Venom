import socket
import sys


def check_port(host, port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        if result == 0:
            print(f"Success: Connected to {host}:{port}")
            sock.close()
            return True
        else:
            print(f"Failure: Could not connect to {host}:{port} (Error code: {result})")
            return False
    except Exception as e:
        print(f"Error: {e}")
        return False


if __name__ == "__main__":
    host = "127.0.0.1"
    port = 8000
    if check_port(host, port):
        sys.exit(0)
    else:
        sys.exit(1)
