"""Open the local application once the web interface is serving."""

import time
import urllib.request
import webbrowser


def main():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(40):
        try:
            with opener.open("http://127.0.0.1:8000/", timeout=2) as response:
                if b"view-editor" in response.read():
                    webbrowser.open("http://127.0.0.1:8000/")
                    return
        except OSError:
            pass
        time.sleep(1)


if __name__ == "__main__":
    main()
