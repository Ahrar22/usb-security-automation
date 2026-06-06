import os
import shutil
import time
import platform
import subprocess
from pathlib import Path
from datetime import datetime

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    print("watchdog is not installed!")
    subprocess.run(["pip", "install", "watchdog"], check=True)
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True


# ─── Settings ──────────────────────────────────────────────────────────────

# Source folders for image backup
SOURCE_FOLDERS = [
    Path.home() / "Pictures",
    Path.home() / "Desktop",
    Path.home() / "Documents",
    Path.home() / "Downloads",
]

# Supported image file extensions
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp",
    ".tiff", ".tif", ".webp", ".heic", ".heif",
    ".raw", ".cr2", ".nef", ".arw", ".dng",
    ".svg", ".ico"
}

# Backup folder name
BACKUP_FOLDER_NAME = "PC_Photos_Backup"

# ─── USB Detection ──────────────────────────────────────────────────────────

def get_usb_drives():
    """List connected USB drives"""
    system = platform.system()
    drives = []

    if system == "Windows":
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if bitmask & 1:
                drive = f"{letter}:\\\\"
                drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
                if drive_type == 2:
                    drives.append(Path(drive))
            bitmask >>= 1

    elif system == "Darwin":
        volumes = Path("/Volumes")
        if volumes.exists():
            for vol in volumes.iterdir():
                if vol.is_mount() and vol.name not in ["Macintosh HD", "Recovery"]:
                    drives.append(vol)

    elif system == "Linux":
        for base in [Path("/media"), Path("/mnt")]:
            if base.exists():
                for item in base.rglob("*"):
                    if item.is_mount():
                        drives.append(item)

    return drives


def get_usb_mount_paths():
    """Return USB mount paths"""
    system = platform.system()
    if system == "Windows":
        return ["C:\\\\"]
    elif system == "Darwin":
        return ["/Volumes"]
    else:
        return ["/media", "/mnt", "/run/media"]


# ─── Copy Images ────────────────────────────────────────────────────────────

def find_images(source_folders):
    """Find all image files"""
    images = []
    for folder in source_folders:
        if not folder.exists():
            continue
        print(f"Searching in: {folder}")
        for file in folder.rglob("*"):
            if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS:
                images.append(file)
    return images


def copy_images_to_usb(usb_path: Path):
    """Copy images to USB"""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_dir = usb_path / BACKUP_FOLDER_NAME / timestamp

    print(f"\n{'='*55}")
    print("Starting image copy process...")
    print(f"Destination: {backup_dir}")
    print(f"{'='*55}\n")

    images = find_images(SOURCE_FOLDERS)

    if not images:
        print("No images found!")
        return

    print(f"{len(images)} images found. Copying...\n")

    backup_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    errors = 0

    for i, img in enumerate(images, 1):
        try:
            relative = None
            for src in SOURCE_FOLDERS:
                try:
                    relative = img.relative_to(src)
                    dest = backup_dir / src.name / relative
                    break
                except ValueError:
                    continue

            if relative is None:
                dest = backup_dir / img.name

            if dest.exists() and dest.stat().st_size == img.stat().st_size:
                skipped += 1
                continue

            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(img, dest)
            copied += 1

            percent = int((i / len(images)) * 100)
            bar = "█" * (percent // 5) + "░" * (20 - percent // 5)
            print(f"\r  [{bar}] {percent}%  ({i}/{len(images)})  {img.name[:40]}", end="", flush=True)

        except Exception as e:
            errors += 1
            print(f"\n  Error copying {img.name}: {e}")

    print(f"\n\n{'='*55}")
    print("Copy completed!")
    print(f"Copied: {copied} files")
    print(f"Skipped: {skipped} existing files")
    print(f"Errors: {errors} files")
    print(f"Destination: {backup_dir}")
    print(f"{'='*55}\n")

    log_file = backup_dir / "backup_log.txt"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"Image Backup - {timestamp}\n")
        f.write(f"Copied: {copied}\n")
        f.write(f"Skipped: {skipped}\n")
        f.write(f"Errors: {errors}\n")
        f.write("\nImage List:\n")
        for img in images:
            f.write(f"  {img}\n")


# ─── USB Monitoring ─────────────────────────────────────────────────────────

class USBWatcher(FileSystemEventHandler):
    """Monitor USB connections"""

    def __init__(self):
        self.known_drives = set(str(d) for d in get_usb_drives())
        print(f"🖥️ Connected USBs: {self.known_drives or 'None'}")

    def on_created(self, event):
        time.sleep(2)
        new_drives = set(str(d) for d in get_usb_drives())
        added = new_drives - self.known_drives

        for drive in added:
            print(f"\n🔌  New USB connected: {drive}")
            self.known_drives.add(drive)
            copy_images_to_usb(Path(drive))


def monitor_usb_windows():
    """Monitor USB on Windows"""
    print("Waiting for USB connection...")
    known = set(str(d) for d in get_usb_drives())

    while True:
        time.sleep(3)
        current = set(str(d) for d in get_usb_drives())
        new = current - known

        for drive in new:
            print(f"\n🔌  New USB connected: {drive}")
            copy_images_to_usb(Path(drive))

        known = current


def monitor_usb_unix():
    """Monitor USB on macOS and Linux"""
    mount_paths = get_usb_mount_paths()
    event_handler = USBWatcher()
    observer = Observer()

    for path in mount_paths:
        if Path(path).exists():
            observer.schedule(event_handler, path, recursive=False)
            print(f"👀  Monitoring: {path}")

    observer.start()
    print("\n✅  Ready! Connect a USB device...\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n👋  Program stopped.")

    observer.join()


# ─── Main Execution ─────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  📸  USB Photo Backup - Automatic Photo Backup")
    print("=" * 55)
    print(f"\n🖥️   Operating System: {platform.system()}")
    print("🏠  Source Folders:")
    for f in SOURCE_FOLDERS:
        status = "✅" if f.exists() else "❌"
        print(f"   {status} {f}")
    print()

    import sys
    if "--now" in sys.argv:
        drives = get_usb_drives()
        if drives:
            copy_images_to_usb(drives[0])
        else:
            print("❌  No USB drive found! Connect a USB and try again.")
        return

    if platform.system() == "Windows":
        monitor_usb_windows()
    else:
        monitor_usb_unix()


if __name__ == "__main__":
    main()
