"""Run application locally for testing and debugging."""

import argparse

from mink import create_app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the application locally for testing and debugging.")
    parser.add_argument("--port", "-p", type=int, default=9000, help="Port to run the application on (default: 9000)")
    parser.add_argument(
        "--host", "-H", type=str, default="localhost", help="Host to run the application on (default: localhost)"
    )
    parser.add_argument("--log-to-file", "-f", action="store_true", help="Log to logfile instead of stdout")
    args = parser.parse_args()

    app = create_app(log_to_file=args.log_to_file)
    app.run(debug=True, host=args.host, port=args.port)
