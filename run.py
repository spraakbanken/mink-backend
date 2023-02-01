"""Run application locally for testing and debugging."""

from mink import create_app

if __name__ == "__main__":
    app = create_app(debug=True)
    app.run(debug=True, host="localhost", port=9000)
