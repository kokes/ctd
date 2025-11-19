from urllib.parse import urlencode
from urllib.request import urlopen
import json
import argparse
import sys
import shutil
import re


BASE_URL = "https://api.ceskatelevize.cz/video/v1/playlist-vod/v1/stream-data/media/external/{video_id}"
PARAMS = {
    "canPlayDrm": "false",
    "quality": "180p",  # audio/audioad/ad/web/mobile/180p/288p/360p/404p/540p/576p/720p/1080p
    "streamType": "progressive",  # dash/hls/progressive/flash/hbbtv/ts
}
HTTP_TIMEOUT = 10
W_MATCH = re.compile(r"\w+")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument("url", metavar="URL", help="URL of the video page")
    args = parser.parse_args()

    url = args.url
    video_id = None
    for part in url.split("/"):
        if part.isdigit():
            video_id = part
            break
    if not video_id:
        print("Could not extract video ID from URL")
        sys.exit(1)

    api_url = BASE_URL.format(video_id=video_id) + "?" + urlencode(PARAMS)
    if args.verbose:
        print(f"API URL: {api_url}")
    with urlopen(api_url, timeout=HTTP_TIMEOUT) as response:
        data = json.load(response)
        title = "_".join(W_MATCH.findall(data["showTitle"]))

        # TODO: better error handling
        assert len(data["streams"]) == 1, "Expected exactly one stream"
        stream = data["streams"][0]

        if args.verbose:
            # TODO: quality 'audio' also available
            for q in stream.get("availableQualities", []):
                print(
                    f"Quality: {q['quality']}, Codec: {q['codec']}, FPS: {q['fps']}, Weight: {q['weight']}"
                )
        stream_url = stream["url"]
        if args.verbose:
            print(f"Stream URL: {stream_url}")

        # TODO: subtitles

        with urlopen(stream_url, timeout=HTTP_TIMEOUT) as stream_response:
            # TODO: error handling
            assert stream_response.headers.get("Content-Type") == "video/mp4"
            length = stream_response.headers.get("Content-Length")
            if not length:
                print("Could not determine content length")
                sys.exit(1)
            length = int(length)

            outfn = f"{title}.mp4"
            if args.verbose:
                print(f"Downloading to: {outfn} ({length} bytes)")
            with open(outfn, "wb") as out_file:
                shutil.copyfileobj(stream_response, out_file)

            # stream_data = stream_response.read()
            # sys.stdout.buffer.write(stream_data)
