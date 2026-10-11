#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p output/frames
blender -b -t 6 --python scripts/build_scene.py > output/render.log 2>&1
python3 scripts/make_audio.py
ffmpeg -y -framerate 12 -i output/frames/frame_%04d.png -i output/room_audio.wav -vf fps=24 -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -c:a aac -b:a 128k -t 10 -movflags +faststart output/bedroom_10s.mp4
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,r_frame_rate,nb_frames -of json output/bedroom_10s.mp4 > output/video_checks.json
