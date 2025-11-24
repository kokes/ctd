import argparse
import json
import re
import sys
from urllib.parse import parse_qsl, urlencode, urlparse
from urllib.request import urlopen

BASE_URL = "https://api.ceskatelevize.cz/video/v1/playlist-vod/v1/stream-data/media/external/{video_id}"

HTTP_TIMEOUT = 10
W_MATCH = re.compile(r"\w+")
CHUNK_SIZE = 1024 * 1024  # 1 MB


# "quality": "180p",  # audio/audioad/ad/web/mobile/180p/288p/360p/404p/540p/576p/720p/1080p
# "streamType": "progressive",  # dash/hls/progressive/flash/hbbtv/ts
# progressive means we get an mp4 container directly, no need to faff with ts fragments
def fetch_video_meta(
    video_id: int,
    quality: str,
    can_play_drm: bool = False,
    stream_type: str = "progressive",
) -> dict:
    params = {
        "canPlayDrm": str(can_play_drm).lower(),
        "quality": quality,
        "streamType": stream_type,
    }
    api_url = BASE_URL.format(video_id=video_id) + "?" + urlencode(params)
    with urlopen(api_url, timeout=HTTP_TIMEOUT) as response:
        data = json.load(response)
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "-q", "--quality", required=False, help="Requested quality, e.g. 720p"
    )
    parser.add_argument(
        "--subtitles", action="store_true", help="Download subtitles if available"
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

    # fetch video metadata without assuming which qualities are available
    data = fetch_video_meta(video_id, quality="web")
    title = "_".join(W_MATCH.findall(data["showTitle"]))

    # TODO: better error handling
    assert len(data["streams"]) == 1, "Expected exactly one stream"
    stream = data["streams"][0]

    qualities: list[str] = [q["quality"] for q in stream.get("availableQualities", [])]
    qualities.append("audio")
    quality = args.quality
    if quality and quality not in qualities:
        print(
            f"Requested quality {quality} not available. Available: {', '.join(qualities)}"
        )
        sys.exit(1)
    if not quality:
        # ask user
        print("Available qualities: " + " ".join(qualities))
        choice = input("Select quality: ")
        quality = choice.strip()
        if quality not in qualities:
            print("Invalid choice")
            sys.exit(1)

    stream_url: str = stream["url"]
    if args.verbose:
        print(f"Original stream URL: {stream_url}")

    parsed_url = urlparse(stream_url)
    query_params = dict(parse_qsl(parsed_url.query))
    query_params["quality"] = quality
    stream_url = parsed_url._replace(query=urlencode(query_params)).geturl()

    # note that the stream URL is now invalidated, because the token is tied to quality
    data = fetch_video_meta(video_id, quality=quality)
    stream_url: str = data["streams"][0]["url"]
    if args.verbose:
        print(f"Final stream URL: {stream_url}")

    if args.subtitles and stream.get("subtitles"):
        assert len(stream["subtitles"]) == 1, "Expected exactly one subtitle track"
        raw_subs = [j for j in stream["subtitles"][0]["files"] if j["format"] == "json"]
        assert len(raw_subs) == 1, "Expected exactly one JSON subtitle file"
        subs_url = raw_subs[0]["url"]
        if args.verbose:
            print(f"Subtitles URL: {subs_url}")
        with urlopen(subs_url, timeout=HTTP_TIMEOUT) as subs_response:
            subs_data = json.load(subs_response)

        subfn = f"{title}.srt"
        if args.verbose:
            print(f"Downloading subtitles to: {subfn}")
        with open(subfn, "wt", encoding="utf-8") as subs_file:
            for item in subs_data:
                subs_file.write(f"{item['id']}\n")
                subs_file.write(f"{item['fromTime']} --> {item['toTime']}\n")
                subs_file.write(f"{item['text']}\n\n")

    with urlopen(stream_url, timeout=HTTP_TIMEOUT) as stream_response:
        # TODO: error handling
        assert stream_response.headers.get("Content-Type") == "video/mp4"
        # TODO: progress bar
        length = stream_response.headers.get("Content-Length")
        if not length:
            print("Could not determine content length")
            sys.exit(1)
        length = int(length)

        outfn = f"{title}.mp4"
        if args.verbose:
            print(f"Downloading to: {outfn} ({length} bytes)")
        with open(outfn, "wb") as out_file:
            # not using shutil, we want to show progress
            # shutil.copyfileobj(stream_response, out_file)

            # poor man's tqdm
            downloaded = 0
            while True:
                chunk = stream_response.read(CHUNK_SIZE)
                if not chunk:
                    break
                out_file.write(chunk)
                downloaded += len(chunk)
                if args.verbose:
                    percent = downloaded * 100 / length
                    print(
                        f"\rDownloaded {downloaded} / {length} bytes ({percent:.2f}%)",
                        end="",
                    )
        print()
