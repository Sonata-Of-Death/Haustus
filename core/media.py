"""Media post-processing and transcoding suite."""
import json
import os
import shutil
import subprocess
from typing import Optional

try:
    from mutagen.id3 import APIC, ID3, TALB, TCON, TIT2, TPE1, USLT
    from mutagen.mp3 import MP3
    from mutagen.mp4 import MP4, MP4Cover
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

class MediaMaestro:
    """Media post-processing suite."""

    def __init__(self, ffmpeg_bin: Optional[str] = None):
        self.ffmpeg = ffmpeg_bin or self._find_ffmpeg()
        self.ffprobe = self._find_ffprobe()
        self.hw_accel = self._detect_hardware_encoder()

    def _find_ffmpeg(self) -> str:
        """Locate portable imageio-ffmpeg or system FFmpeg executable."""
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
        return shutil.which("ffmpeg") or "ffmpeg"

    def _find_ffprobe(self) -> str:
        """Locate ffprobe executable."""
        return shutil.which("ffprobe") or "ffprobe"

    def _detect_hardware_encoder(self) -> str:
        """Detect available hardware encoders via FFmpeg probe."""
        try:
            res = subprocess.run(
                [self.ffmpeg, "-encoders"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="ignore"
            )
            output = res.stdout.lower()
            if "hevc_nvenc" in output or "av1_nvenc" in output:
                return "nvenc"
            elif "hevc_videotoolbox" in output:
                return "videotoolbox"
            elif "hevc_vaapi" in output:
                return "vaapi"
            elif "hevc_qsv" in output:
                return "qsv"
        except Exception:
            pass
        return "software"


    def transcode_video(
        self,
        input_path: str,
        output_path: str,
        target_codec: str = "hevc",
        target_crf: int = 23,
        preset: str = "p7",
        faststart: bool = True
    ) -> bool:
        """Transcode video using ffmpeg."""
        if not os.path.isfile(input_path):
            return False

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        cmd = [self.ffmpeg, "-y", "-hwaccel", "auto", "-i", input_path]

        if self.hw_accel == "nvenc":
            enc = "av1_nvenc" if target_codec.lower() == "av1" else "hevc_nvenc"
            cmd.extend([
                "-c:v", enc,
                "-preset", preset,
                "-rc", "vbr",
                "-cq", str(target_crf),
                "-spatial_aq", "1",
                "-temporal_aq", "1"
            ])
        elif self.hw_accel == "videotoolbox":
            cmd.extend(["-c:v", "hevc_videotoolbox", "-q:v", "65"])
        elif self.hw_accel == "vaapi":
            cmd.extend([
                "-vaapi_device", "/dev/dri/renderD128",
                "-vf", "format=nv12,hwupload",
                "-c:v", "hevc_vaapi",
                "-qp", str(target_crf)
            ])
        else:
            # Fall back to software encoding.
            if target_codec.lower() == "av1":
                cmd.extend([
                    "-c:v", "libsvtav1",
                    "-preset", "6",
                    "-crf", str(target_crf + 4),
                    "-pix_fmt", "yuv420p10le"
                ])
            else:
                cmd.extend([
                    "-c:v", "libx265",
                    "-preset", "medium",
                    "-crf", str(target_crf),
                    "-pix_fmt", "yuv420p"
                ])

        cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        if faststart:
            cmd.extend(["-movflags", "+faststart"])
        cmd.append(output_path)

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return res.returncode == 0 and os.path.isfile(output_path)


    def normalize_audio(
        self,
        input_path: str,
        output_path: str,
        target_i: float = -16.0,
        target_tp: float = -1.5,
        target_lra: float = 11.0,
        trim_silence: bool = True,
        audio_format: str = "mp3",
        bitrate: str = "320"
    ) -> bool:
        """Normalize audio loudness to EBU R128."""
        if not os.path.isfile(input_path):
            return False

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        # First pass measures integrated loudness and true peak levels.
        pass1_cmd = [
            self.ffmpeg, "-i", input_path,
            "-af", f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
            "-f", "null", "-"
        ]
        p1 = subprocess.run(pass1_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="ignore")
        stderr_txt = p1.stderr

        json_start = stderr_txt.rfind("{")
        json_end = stderr_txt.rfind("}")
        if json_start == -1 or json_end == -1:
            return False

        try:
            stats = json.loads(stderr_txt[json_start:json_end + 1])
        except Exception:
            return False

        af_filters = []
        if trim_silence:
            af_filters.append(
                "silenceremove=start_periods=1:start_duration=0.3:start_threshold=-50dB:"
                "stop_periods=1:stop_duration=0.5:stop_threshold=-50dB"
            )

        af_filters.append(
            f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:"
            f"measured_I={stats.get('input_i', -24)}:measured_TP={stats.get('input_tp', -1)}:"
            f"measured_LRA={stats.get('input_lra', 7)}:measured_thresh={stats.get('input_thresh', -34)}:"
            f"offset={stats.get('target_offset', 0)}:linear=true"
        )
        filter_str = ",".join(af_filters)

        # Second pass applies measured linear normalization.
        pass2_cmd = [self.ffmpeg, "-y", "-i", input_path, "-af", filter_str]

        fmt = audio_format.lower()
        if fmt == "mp3":
            pass2_cmd.extend(["-c:a", "libmp3lame", "-b:a", f"{bitrate}k" if bitrate != "best" else "320k"])
        elif fmt == "m4a":
            pass2_cmd.extend(["-c:a", "aac", "-b:a", f"{bitrate}k" if bitrate != "best" else "256k"])
        elif fmt == "flac":
            pass2_cmd.extend(["-c:a", "flac"])
        elif fmt == "wav":
            pass2_cmd.extend(["-c:a", "pcm_s16le"])
        elif fmt == "opus":
            pass2_cmd.extend(["-c:a", "libopus", "-b:a", f"{bitrate}k" if bitrate != "best" else "160k"])
        else:
            pass2_cmd.extend(["-c:a", "libmp3lame", "-b:a", "320k"])

        pass2_cmd.append(output_path)
        p2 = subprocess.run(pass2_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return p2.returncode == 0 and os.path.isfile(output_path)


    def tag_audio_file(
        self,
        audio_path: str,
        title: str,
        artist: str,
        album: str = "Media Vault",
        cover_image_path: Optional[str] = None,
        lyrics: Optional[str] = None
    ) -> bool:
        """Inject full ID3v2.4 tags and album artwork into MP3."""
        if not MUTAGEN_AVAILABLE or not os.path.isfile(audio_path):
            return False

        try:
            audio = MP3(audio_path, ID3=ID3)
            try:
                audio.add_tags()
            except Exception:
                pass

            audio.tags.add(TIT2(encoding=3, text=title))
            audio.tags.add(TPE1(encoding=3, text=artist))
            audio.tags.add(TALB(encoding=3, text=album))
            audio.tags.add(TCON(encoding=3, text="Media Master"))

            if lyrics:
                audio.tags.add(USLT(encoding=3, lang="eng", desc="Transcription", text=lyrics))

            if cover_image_path and os.path.isfile(cover_image_path):
                with open(cover_image_path, "rb") as img:
                    img_data = img.read()
                mime = "image/png" if cover_image_path.lower().endswith(".png") else "image/jpeg"
                audio.tags.add(APIC(
                    encoding=3,
                    mime=mime,
                    type=3,
                    desc="Cover Art",
                    data=img_data
                ))

            audio.save(v2_version=4)
            return True
        except Exception:
            return False

    def tag_mp4_video(
        self,
        video_path: str,
        title: str,
        artist: str,
        cover_image_path: Optional[str] = None
    ) -> bool:
        """Inject metadata and thumbnail atom into MP4 container."""
        if not MUTAGEN_AVAILABLE or not os.path.isfile(video_path):
            return False

        try:
            mp4 = MP4(video_path)
            mp4["\xa9nam"] = [title]
            mp4["\xa9ART"] = [artist]
            mp4["\xa9alb"] = ["Social Media Archive"]

            if cover_image_path and os.path.isfile(cover_image_path):
                with open(cover_image_path, "rb") as img:
                    img_data = img.read()
                cov_fmt = MP4Cover.FORMAT_PNG if cover_image_path.lower().endswith(".png") else MP4Cover.FORMAT_JPEG
                mp4["covr"] = [MP4Cover(img_data, imageformat=cov_fmt)]

            mp4.save()
            return True
        except Exception:
            return False
