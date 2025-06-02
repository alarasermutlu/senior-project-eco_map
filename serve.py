from http.server import HTTPServer, SimpleHTTPRequestHandler
import webbrowser
import os
import socket
import sys

def find_available_port(start_port=8000, max_port=8999):
    """Find an available port in the given range."""
    for port in range(start_port, max_port + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    raise RuntimeError("No available ports found")

def run(server_class=HTTPServer, handler_class=SimpleHTTPRequestHandler):
    try:
        # Find an available port
        port = find_available_port()
        server_address = ('', port)
        httpd = server_class(server_address, handler_class)
        
        print(f"Starting server at http://localhost:{port}/")
        print("Press Ctrl+C to stop the server")
        
        # Open the browser
        url = f'http://localhost:{port}/map.html'
        print(f"Opening {url} in your browser...")
        webbrowser.open(url)
        
        # Start the server
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()
        sys.exit(0)
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    run() 