"""
Firewire Controller - Storage Manager
Detects external USB-attached microSD cards, mounts them, and handles formatting.
"""

import logging
import os
import pathlib
import subprocess
import time

import config

log = logging.getLogger(__name__)


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    log.debug("Running: %s", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120, **kwargs)


def _find_usb_block_devices() -> list[str]:
    """
    Return a list of block device paths (e.g. ['/dev/sda']) that are
    connected via USB.  We inspect sysfs to find devices whose transport
    is usb.
    """
    devices = []
    block_dir = pathlib.Path("/sys/block")
    for entry in sorted(block_dir.iterdir()):
        # Skip non-removable virtual / mmc devices
        name = entry.name
        if name.startswith(("loop", "ram", "mmcblk", "zram")):
            continue
        # Walk the device tree looking for a "usb" ancestor
        device_path = entry.resolve()
        if "usb" in str(device_path):
            dev_path = f"/dev/{name}"
            if os.path.exists(dev_path):
                devices.append(dev_path)
    return devices


def _first_partition(dev: str) -> str | None:
    """Return the first partition device node, e.g. /dev/sda1, or None."""
    # Try common partition naming: sda1, sdb1, ...
    p1 = f"{dev}1"
    if os.path.exists(p1):
        return p1
    # If the whole disk is formatted without partitions, return the disk itself
    return dev


def detect_external_sd() -> dict | None:
    """
    Detect the first USB-connected microSD card.
    Returns dict with keys: 'device', 'partition', 'mount_point', 'save_dir'
    or None if nothing found.
    """
    usb_devs = _find_usb_block_devices()
    if not usb_devs:
        log.warning("No USB block devices detected")
        return None

    dev = usb_devs[0]
    partition = _first_partition(dev)
    log.info("Detected external USB storage: dev=%s partition=%s", dev, partition)

    mount_point = config.MOUNT_BASE
    save_dir = os.path.join(mount_point, config.SAVE_DIR_NAME)

    return {
        "device": dev,
        "partition": partition,
        "mount_point": mount_point,
        "save_dir": save_dir,
    }


def mount_storage(info: dict) -> bool:
    """Ensure the external microSD is mounted and the save directory exists."""
    mp = info["mount_point"]
    part = info["partition"]

    os.makedirs(mp, exist_ok=True)

    # Check if the correct partition is already mounted here
    result = _run(["findmnt", "-rn", "-o", "SOURCE", mp])
    mounted_source = result.stdout.strip() if result.returncode == 0 else ""

    if mounted_source == part:
        log.info("Already mounted: %s on %s", part, mp)
    else:
        if mounted_source:
            # findmnt found a different device (e.g. parent filesystem) – mount over it
            log.info("Mount point %s has %s (expected %s), mounting correct device",
                     mp, mounted_source, part)
        result = _run(["mount", part, mp])
        if result.returncode != 0:
            log.error("Failed to mount %s: %s", part, result.stderr)
            return False
        log.info("Mounted %s on %s", part, mp)

    # Ensure captures subdirectory
    save_dir = info["save_dir"]
    os.makedirs(save_dir, exist_ok=True)
    log.info("Save directory ready: %s", save_dir)
    return True


def unmount_storage(info: dict) -> bool:
    """Unmount the external microSD."""
    mp = info["mount_point"]
    result = _run(["umount", mp])
    if result.returncode != 0:
        log.warning("umount failed: %s", result.stderr)
        # Force lazy unmount
        _run(["umount", "-l", mp])
    return True


def format_storage(info: dict) -> bool:
    """
    Format the external microSD card as exFAT with label DVMEDIA.
    Unmounts first, wipes partition table, creates single partition, formats.
    Returns True on success.
    """
    dev = info["device"]       # e.g. /dev/sda
    part = info["partition"]   # e.g. /dev/sda1

    log.info("Starting format of %s", dev)

    # 1. Unmount
    unmount_storage(info)

    # 2. Wipe and create fresh partition table + single partition
    # Use sfdisk for scripted partitioning
    _run(["wipefs", "--all", "--force", dev])

    sfdisk_input = "label: dos\ntype=07\n"  # 0x07 = exFAT/NTFS partition type
    result = _run(["sfdisk", "--force", dev], input=sfdisk_input)
    if result.returncode != 0:
        log.error("sfdisk failed: %s", result.stderr)
        return False

    # Re-read partition table
    _run(["partprobe", dev])
    time.sleep(2)

    # Re-detect partition
    part = _first_partition(dev)
    if not part:
        log.error("No partition found after sfdisk")
        return False

    # 3. Format as exFAT
    result = _run(["mkfs.exfat", "-n", config.FS_LABEL, part])
    if result.returncode != 0:
        log.error("mkfs.exfat failed: %s", result.stderr)
        return False

    log.info("Format complete: %s as exFAT label=%s", part, config.FS_LABEL)

    # 4. Update partition reference and remount
    info["partition"] = part
    return mount_storage(info)


def is_storage_present(info: dict) -> bool:
    """
    Check whether the external drive is still physically present and mounted.
    Returns False if the partition device node has disappeared or the mount
    point is no longer active.
    """
    partition = info.get("partition")
    mount_point = info.get("mount_point")

    if not partition or not os.path.exists(partition):
        log.warning("Storage device %s no longer exists", partition)
        return False

    if not mount_point or not os.path.ismount(mount_point):
        log.warning("Mount point %s is no longer mounted", mount_point)
        return False

    return True


def get_free_space_mb(info: dict) -> int:
    """Return free space in MB on the mounted storage."""
    try:
        st = os.statvfs(info["mount_point"])
        return (st.f_bavail * st.f_frsize) // (1024 * 1024)
    except OSError:
        return 0
