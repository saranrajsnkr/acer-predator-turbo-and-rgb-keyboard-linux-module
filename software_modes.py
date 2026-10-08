#!/usr/bin/env python3
"""
Software-Composed RGB Keyboard Modes for Acer Predator.

These modes create new lighting effects by rapidly cycling the existing
hardware modes (Static per-zone coloring and dynamic modes) from Python.

Since these are software-driven, they use a small amount of CPU and won't
be as smooth as firmware-level animations, but they can produce effects
that the firmware doesn't natively support.

Usage:
    sudo python3 software_modes.py

Press Ctrl+C at any time to stop the animation and exit.
"""

import colorsys
import math
import os
import random
import signal
import sys
from time import sleep, time

PAYLOAD_SIZE = 16
CHARACTER_DEVICE = "/dev/acer-gkbbl-0"

PAYLOAD_SIZE_STATIC = 4
CHARACTER_DEVICE_STATIC = "/dev/acer-gkbbl-static-0"

NUM_ZONES = 4

# Flag to gracefully stop animation loops
_running = True


def _signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    global _running
    _running = False
    print("\n\nStopping animation...")


signal.signal(signal.SIGINT, _signal_handler)


def _write_dynamic(mode, speed, brightness, direction=1, red=0, green=0, blue=0):
    """Write a dynamic (non-static) mode payload to the kernel module."""
    payload = [0] * PAYLOAD_SIZE
    payload[0] = mode
    payload[1] = speed
    payload[2] = brightness
    payload[3] = 8 if mode == 3 else 0
    payload[4] = direction
    payload[5] = red
    payload[6] = green
    payload[7] = blue
    payload[9] = 1
    try:
        with open(CHARACTER_DEVICE, 'wb') as cd:
            cd.write(bytes(payload))
    except PermissionError:
        print("Error: Permission denied. Run with sudo.")
        sys.exit(1)
    except FileNotFoundError:
        print(f"Error: {CHARACTER_DEVICE} not found. Is the facer kernel module loaded?")
        sys.exit(1)


def _write_static_zone(zone_id, red, green, blue, brightness=100):
    """
    Write a static color to a specific zone (1-4).
    Also sends the dynamic payload to tell the firmware to use static mode.
    """
    payload_static = [0] * PAYLOAD_SIZE_STATIC
    payload_static[0] = 1 << (zone_id - 1)
    payload_static[1] = red
    payload_static[2] = green
    payload_static[3] = blue
    try:
        with open(CHARACTER_DEVICE_STATIC, 'wb') as cd:
            cd.write(bytes(payload_static))
    except PermissionError:
        print("Error: Permission denied. Run with sudo.")
        sys.exit(1)
    except FileNotFoundError:
        print(f"Error: {CHARACTER_DEVICE_STATIC} not found. Is the facer kernel module loaded?")
        sys.exit(1)

    # Tell WMI to use static coloring
    payload = [0] * PAYLOAD_SIZE
    payload[2] = brightness
    payload[9] = 1
    with open(CHARACTER_DEVICE, 'wb') as cd:
        cd.write(bytes(payload))


def _write_all_zones(colors, brightness=100):
    """
    Set all 4 zones to specific colors at once.
    colors: list of 4 tuples [(r, g, b), (r, g, b), (r, g, b), (r, g, b)]
    """
    for zone_id in range(1, NUM_ZONES + 1):
        r, g, b = colors[zone_id - 1]
        payload_static = [0] * PAYLOAD_SIZE_STATIC
        payload_static[0] = 1 << (zone_id - 1)
        payload_static[1] = int(r)
        payload_static[2] = int(g)
        payload_static[3] = int(b)
        try:
            with open(CHARACTER_DEVICE_STATIC, 'wb') as cd:
                cd.write(bytes(payload_static))
        except (PermissionError, FileNotFoundError):
            return

    # Tell WMI to use static coloring
    payload = [0] * PAYLOAD_SIZE
    payload[2] = brightness
    payload[9] = 1
    try:
        with open(CHARACTER_DEVICE, 'wb') as cd:
            cd.write(bytes(payload))
    except (PermissionError, FileNotFoundError):
        return


def _hue_to_rgb(hue):
    """Convert a hue (0.0–1.0) to an (R, G, B) tuple (0–255)."""
    r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    return (int(r * 255), int(g * 255), int(b * 255))


def _clamp(value, min_val=0, max_val=255):
    """Clamp a value between min and max."""
    return max(min_val, min(max_val, int(value)))


# =============================================================================
# Software Mode 1: Rainbow Cycle
# =============================================================================
def rainbow_cycle(speed=0.05, brightness=100):
    """
    Rotate rainbow hues across all 4 keyboard zones.
    Each zone gets a different part of the spectrum, and the colors
    smoothly rotate over time.

    speed: delay between frames in seconds (lower = faster)
    brightness: keyboard brightness (0-100)
    """
    global _running
    _running = True
    hue_offset = 0.0
    print("🌈 Rainbow Cycle — Press Ctrl+C to stop")

    while _running:
        colors = []
        for zone in range(NUM_ZONES):
            hue = (hue_offset + zone / NUM_ZONES) % 1.0
            colors.append(_hue_to_rgb(hue))
        _write_all_zones(colors, brightness)
        hue_offset = (hue_offset + 0.02) % 1.0
        sleep(speed)


# =============================================================================
# Software Mode 2: Color Strobe / Flash
# =============================================================================
def color_strobe(red=255, green=255, blue=255, frequency=0.1, brightness=100):
    """
    Rapid on/off blinking of a single color across all zones.

    red, green, blue: the color to strobe (0-255 each)
    frequency: time in seconds for each on/off cycle (lower = faster)
    brightness: keyboard brightness (0-100)
    """
    global _running
    _running = True
    print("⚡ Color Strobe — Press Ctrl+C to stop")
    on_color = (red, green, blue)
    off_color = (0, 0, 0)

    while _running:
        _write_all_zones([on_color] * NUM_ZONES, brightness)
        sleep(frequency)
        if not _running:
            break
        _write_all_zones([off_color] * NUM_ZONES, 0)
        sleep(frequency)


# =============================================================================
# Software Mode 3: Police Siren
# =============================================================================
def police_siren(speed=0.15, brightness=100):
    """
    Alternating red and blue across zones, simulating a police siren effect.
    Left two zones flash red, right two flash blue, then they swap.

    speed: delay between swaps in seconds
    brightness: keyboard brightness (0-100)
    """
    global _running
    _running = True
    print("🚨 Police Siren — Press Ctrl+C to stop")
    red = (255, 0, 0)
    blue = (0, 0, 255)
    off = (0, 0, 0)

    while _running:
        # Phase 1: Left red, Right blue
        _write_all_zones([red, red, blue, blue], brightness)
        sleep(speed)
        if not _running:
            break

        # Brief off
        _write_all_zones([off, off, off, off], 0)
        sleep(speed * 0.3)
        if not _running:
            break

        # Phase 2: Left blue, Right red
        _write_all_zones([blue, blue, red, red], brightness)
        sleep(speed)
        if not _running:
            break

        # Brief off
        _write_all_zones([off, off, off, off], 0)
        sleep(speed * 0.3)


# =============================================================================
# Software Mode 4: Campfire
# =============================================================================
def campfire(speed=0.08, brightness=100):
    """
    Warm orange/red/yellow flickering effect that simulates a campfire.
    Uses random brightness and slight color variations per zone.

    speed: base delay between frames
    brightness: maximum keyboard brightness (0-100)
    """
    global _running
    _running = True
    print("🔥 Campfire — Press Ctrl+C to stop")

    # Warm palette: shades of red, orange, yellow
    warm_colors = [
        (255, 60, 0),    # deep orange
        (255, 100, 0),   # orange
        (255, 140, 0),   # light orange
        (255, 40, 0),    # red-orange
        (255, 80, 10),   # warm orange
        (200, 30, 0),    # dark red
        (255, 120, 20),  # amber
        (255, 160, 30),  # gold
    ]

    while _running:
        colors = []
        for _ in range(NUM_ZONES):
            base = random.choice(warm_colors)
            # Add slight random variation
            r = _clamp(base[0] + random.randint(-20, 20))
            g = _clamp(base[1] + random.randint(-15, 15))
            b = _clamp(base[2] + random.randint(-5, 5))
            colors.append((r, g, b))
        # Random brightness flicker
        flicker_brightness = _clamp(
            brightness + random.randint(-30, 10), min_val=30, max_val=100
        )
        _write_all_zones(colors, flicker_brightness)
        sleep(speed + random.uniform(-0.03, 0.05))


# =============================================================================
# Software Mode 5: Random Sparkle
# =============================================================================
def random_sparkle(speed=0.06, brightness=100):
    """
    Randomly set individual zones to random colors in quick succession,
    creating a sparkling / glitter effect.

    speed: delay between sparkle updates
    brightness: keyboard brightness (0-100)
    """
    global _running
    _running = True
    print("✨ Random Sparkle — Press Ctrl+C to stop")

    # Current colors for all zones (start dark)
    current_colors = [(0, 0, 0)] * NUM_ZONES

    while _running:
        # Pick a random zone to "sparkle"
        zone = random.randint(0, NUM_ZONES - 1)
        # Random bright color
        r = random.randint(100, 255)
        g = random.randint(100, 255)
        b = random.randint(100, 255)
        current_colors[zone] = (r, g, b)
        _write_all_zones(current_colors, brightness)
        sleep(speed)

        if not _running:
            break

        # Fade that zone back toward dark
        current_colors[zone] = (
            max(0, current_colors[zone][0] - 80),
            max(0, current_colors[zone][1] - 80),
            max(0, current_colors[zone][2] - 80),
        )


# =============================================================================
# Software Mode 6: Gradient Sweep
# =============================================================================
def gradient_sweep(color1=(255, 0, 0), color2=(0, 0, 255), speed=0.05, brightness=100):
    """
    Smooth color transition across zones from color1 to color2,
    sweeping back and forth continuously.

    color1: starting RGB tuple
    color2: ending RGB tuple
    speed: delay between frames
    brightness: keyboard brightness (0-100)
    """
    global _running
    _running = True
    print("🎨 Gradient Sweep — Press Ctrl+C to stop")
    t = 0.0

    while _running:
        colors = []
        for zone in range(NUM_ZONES):
            # Calculate position in the gradient wave
            pos = (math.sin(t + zone * 0.8) + 1) / 2  # 0.0 to 1.0
            r = int(color1[0] + (color2[0] - color1[0]) * pos)
            g = int(color1[1] + (color2[1] - color1[1]) * pos)
            b = int(color1[2] + (color2[2] - color1[2]) * pos)
            colors.append((_clamp(r), _clamp(g), _clamp(b)))
        _write_all_zones(colors, brightness)
        t += 0.08
        sleep(speed)


# =============================================================================
# Software Mode 7: Dual-Color Wave
# =============================================================================
def dual_color_wave(
    color1=(255, 0, 0), color2=(0, 255, 0), speed=0.1, brightness=100
):
    """
    A wave-like pattern alternating between two user-chosen colors
    across the keyboard zones.

    color1: first RGB tuple
    color2: second RGB tuple
    speed: delay between frames
    brightness: keyboard brightness (0-100)
    """
    global _running
    _running = True
    print("🌊 Dual-Color Wave — Press Ctrl+C to stop")
    step = 0

    while _running:
        colors = []
        for zone in range(NUM_ZONES):
            # Create a moving wave pattern
            wave = (math.sin((step + zone * 2) * 0.3) + 1) / 2
            r = int(color1[0] * (1 - wave) + color2[0] * wave)
            g = int(color1[1] * (1 - wave) + color2[1] * wave)
            b = int(color1[2] * (1 - wave) + color2[2] * wave)
            colors.append((_clamp(r), _clamp(g), _clamp(b)))
        _write_all_zones(colors, brightness)
        step += 1
        sleep(speed)


# =============================================================================
# Software Mode 8: Custom Pulse
# =============================================================================
def custom_pulse(red=0, green=255, blue=255, speed=0.03, brightness=100):
    """
    A breathing/pulse effect with custom easing — the color smoothly
    brightens and dims using a sine wave for natural-looking pulsation.
    Unlike the hardware Breath mode, you have full control over the
    pulse speed and color.

    red, green, blue: the color to pulse (0-255 each)
    speed: delay between brightness steps
    brightness: maximum keyboard brightness (0-100)
    """
    global _running
    _running = True
    print("💫 Custom Pulse — Press Ctrl+C to stop")
    t = 0.0

    while _running:
        # Sine wave easing for smooth pulse (0 → 1 → 0)
        intensity = (math.sin(t) + 1) / 2  # 0.0 to 1.0
        r = int(red * intensity)
        g = int(green * intensity)
        b = int(blue * intensity)
        pulse_brightness = int(brightness * intensity)
        pulse_brightness = max(pulse_brightness, 1)  # Minimum 1 to avoid fully off

        color = (_clamp(r), _clamp(g), _clamp(b))
        _write_all_zones([color] * NUM_ZONES, _clamp(pulse_brightness, 0, 100))
        t += 0.1
        sleep(speed)


# =============================================================================
# Software Mode 9: Ambient Display
# =============================================================================
def _boost_saturation(r, g, b, factor=1.5):
    """
    Boost the saturation of an RGB color to make it more vibrant
    on the keyboard LEDs (which tend to look washed out with pale colors).
    """
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    s = min(1.0, s * factor)  # Boost saturation
    v = min(1.0, max(0.15, v))  # Ensure minimum visibility
    nr, ng, nb = colorsys.hsv_to_rgb(h, s, v)
    return (int(nr * 255), int(ng * 255), int(nb * 255))


def _smooth_color(prev, curr, alpha=0.3):
    """
    Smooth transition between previous and current color to reduce flicker.
    alpha: blending factor (0.0 = keep old, 1.0 = use new immediately)
    """
    return (
        int(prev[0] * (1 - alpha) + curr[0] * alpha),
        int(prev[1] * (1 - alpha) + curr[1] * alpha),
        int(prev[2] * (1 - alpha) + curr[2] * alpha),
    )


def ambient_display(speed=0.05, brightness=100, sample_region="bottom",
                    saturation_boost=1.5, smoothing=0.3):
    """
    Ambient Display mode — mirrors your screen colors onto the keyboard.

    Captures a screenshot, divides it into 4 vertical strips matching the
    4 keyboard zones (left to right), computes the average color of each
    strip, and sets the corresponding zone to that color in real-time.

    This creates a live Ambilight-style effect where your keyboard
    reflects what's on your display.

    speed: delay between screen captures (lower = more responsive, more CPU)
    brightness: keyboard brightness (0-100)
    sample_region: which part of the screen to sample
        "bottom" — bottom 40% (closest to keyboard, best for most use)
        "full"   — entire screen
        "top"    — top 40%
    saturation_boost: multiplier for color saturation (1.0 = no boost,
        1.5 = recommended, makes colors more vivid on LEDs)
    smoothing: how much to smooth transitions (0.0 = instant, 1.0 = very slow)
        Recommended: 0.3 for a balance of responsiveness and smoothness
    """
    global _running
    _running = True

    # Try to import screen capture library
    try:
        from PIL import ImageGrab
    except ImportError:
        print("Error: Pillow is required for Ambient Display mode.")
        print("Install it with: pip3 install Pillow")
        return

    print("🖥️  Ambient Display — Press Ctrl+C to stop")
    print(f"   Sampling: {sample_region} of screen")
    print(f"   Saturation boost: {saturation_boost}x")
    print(f"   Smoothing: {smoothing}")
    print(f"   Update rate: {1/speed:.0f} fps")
    print()

    # Previous frame colors for smoothing
    prev_colors = [(0, 0, 0)] * NUM_ZONES

    while _running:
        try:
            # Capture the screen
            screenshot = ImageGrab.grab()
            width, height = screenshot.size

            # Determine the vertical region to sample
            if sample_region == "bottom":
                y_start = int(height * 0.6)
                y_end = height
            elif sample_region == "top":
                y_start = 0
                y_end = int(height * 0.4)
            else:  # "full"
                y_start = 0
                y_end = height

            # Divide the screen into 4 vertical strips (one per zone)
            strip_width = width // NUM_ZONES
            colors = []

            for zone in range(NUM_ZONES):
                x_start = zone * strip_width
                x_end = (zone + 1) * strip_width if zone < NUM_ZONES - 1 else width

                # Crop to this zone's strip
                strip = screenshot.crop((x_start, y_start, x_end, y_end))

                # Downscale for faster average calculation
                # Resize to a tiny image — PIL computes the average during resize
                small = strip.resize((1, 1))
                avg_color = small.getpixel((0, 0))

                # Handle RGBA (some systems return 4 channels)
                r, g, b = avg_color[0], avg_color[1], avg_color[2]

                # Boost saturation for more vibrant LED colors
                if saturation_boost != 1.0:
                    r, g, b = _boost_saturation(r, g, b, saturation_boost)

                colors.append((_clamp(r), _clamp(g), _clamp(b)))

            # Apply smoothing to reduce jitter
            smoothed_colors = []
            for i in range(NUM_ZONES):
                smoothed = _smooth_color(prev_colors[i], colors[i], smoothing)
                smoothed_colors.append(smoothed)
            prev_colors = smoothed_colors

            _write_all_zones(smoothed_colors, brightness)

        except Exception as e:
            # Don't crash on transient screenshot failures
            # (e.g., screen locked, compositor switching)
            pass

        sleep(speed)


# =============================================================================
# Software Mode 10: Ambient Music Visualizer
# =============================================================================
def _get_pulse_monitor_source():
    """
    Find the PulseAudio/PipeWire monitor source for system audio output.
    Returns the monitor source name, or None if not found.
    """
    import subprocess
    try:
        result = subprocess.run(
            ['pactl', 'get-default-sink'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            default_sink = result.stdout.strip()
            return f"{default_sink}.monitor"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: search for any monitor source
    try:
        result = subprocess.run(
            ['pactl', 'list', 'short', 'sources'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if '.monitor' in line:
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        return parts[1]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


def _intensity_to_hue(intensity):
    """
    Map beat intensity (0.0–1.0) to a hue value.
    Low intensity → calm blue (0.6)
    Medium intensity → green/cyan (0.4–0.3)
    High intensity → red/magenta (0.0 / 0.9)

    Returns hue in range 0.0–1.0.
    """
    # Map: 0.0 → 0.6 (blue), 0.5 → 0.3 (green/cyan), 1.0 → 0.95 (magenta-red)
    if intensity < 0.5:
        # Blue (0.6) → Cyan/Green (0.3)
        hue = 0.6 - (intensity * 2) * 0.3
    else:
        # Green (0.3) → Red (0.0) → Magenta (0.95)
        t = (intensity - 0.5) * 2  # 0.0 to 1.0
        if t < 0.7:
            # Green (0.3) → Red (0.0)
            hue = 0.3 - (t / 0.7) * 0.3
        else:
            # Red (0.0) → Magenta (0.95)
            hue = 1.0 - (1.0 - t) / 0.3 * 0.05
    return max(0.0, min(1.0, hue))


def music_visualizer(sensitivity=1.5, brightness=100, smoothing=0.4):
    """
    Ambient Music Visualizer — reacts to system audio in real-time.

    Captures audio from PulseAudio/PipeWire system output, performs
    real-time analysis, and makes the entire keyboard light up and
    blink in sync with the music beat.

    The whole keyboard reacts as one:
        - Brightness pulses with the beat energy
        - Color shifts dynamically based on intensity:
            Calm (low energy)  → Blue / Cyan
            Medium energy      → Green / Yellow
            High energy (beat) → Red / Magenta

    Requirements:
        pip3 install numpy pyaudio

    sensitivity: multiplier for audio reactivity (higher = more reactive)
    brightness: maximum keyboard brightness (0-100)
    smoothing: transition smoothing (0.0 = instant, 1.0 = very slow)
    """
    global _running
    _running = True

    # Check dependencies
    try:
        import numpy as np
    except ImportError:
        print("Error: NumPy is required for Music Visualizer mode.")
        print("Install it with: pip3 install numpy")
        return

    try:
        import pyaudio
    except ImportError:
        print("Error: PyAudio is required for Music Visualizer mode.")
        print("Install it with: pip3 install pyaudio")
        print("On Debian/Ubuntu, you may also need: sudo apt install portaudio19-dev")
        return

    # Audio capture settings
    RATE = 44100           # Sample rate
    CHUNK = 2048           # Samples per frame (~46ms at 44100Hz)
    FORMAT = pyaudio.paInt16
    CHANNELS = 1

    # Find the monitor source
    monitor_source = _get_pulse_monitor_source()
    if monitor_source is None:
        print("Error: Could not find PulseAudio/PipeWire monitor source.")
        print("Make sure PulseAudio or PipeWire is running.")
        print("You can check with: pactl list short sources")
        return

    print("🎵 Ambient Music Visualizer — Press Ctrl+C to stop")
    print(f"   Audio source: {monitor_source}")
    print(f"   Sensitivity: {sensitivity}x")
    print(f"   Smoothing: {smoothing}")
    print(f"   Mode: Full keyboard — all zones react together")
    print()

    # Set PULSE_SOURCE so PulseAudio/PipeWire routes from the monitor sink.
    # PyAudio doesn't list monitor sources by their pactl names, but setting
    # this env var tells the PulseAudio backend which source to capture from.
    os.environ['PULSE_SOURCE'] = monitor_source

    # Initialize PyAudio (suppress ALSA/JACK warnings to stderr)
    import contextlib, io as _io
    _devnull = open(os.devnull, 'w')
    _old_stderr = os.dup(2)
    os.dup2(_devnull.fileno(), 2)
    pa = pyaudio.PyAudio()
    os.dup2(_old_stderr, 2)
    _devnull.close()

    try:
        stream = pa.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )
    except Exception as e:
        print(f"Error opening audio stream: {e}")
        print("\nAvailable input devices:")
        for i in range(pa.get_device_count()):
            dev_info = pa.get_device_info_by_index(i)
            if dev_info.get('maxInputChannels') > 0:
                print(f"  [{i}] {dev_info['name']}")
        pa.terminate()
        return

    print("   ✓ Audio stream opened successfully. Play some music!\n")

    # State for smoothing
    prev_level = 0.0
    prev_color = (0, 0, 50)  # Start with dim blue
    peak_level = 0.01        # For auto-gain normalization

    try:
        while _running:
            try:
                # Read audio data
                data = stream.read(CHUNK, exception_on_overflow=False)
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float64)

                # Calculate RMS (Root Mean Square) energy of the entire signal
                rms = np.sqrt(np.mean(samples ** 2))

                # Also get bass-weighted energy for punchier beat response
                # Apply Hanning window and FFT
                window = np.hanning(len(samples))
                fft_data = np.abs(np.fft.rfft(samples * window))
                fft_data = fft_data / (CHUNK / 2)

                # Weight bass frequencies (20-300Hz) more heavily for beat detection
                freq_resolution = RATE / CHUNK
                bass_low = max(1, int(20 / freq_resolution))
                bass_high = min(CHUNK // 2, int(300 / freq_resolution))
                bass_energy = np.mean(fft_data[bass_low:bass_high + 1])

                # Combine RMS and bass energy for the overall level
                # Bass gets 60% weight for punchier beat response
                raw_level = (rms / 32768.0 * 0.4 + bass_energy / 100.0 * 0.6) * sensitivity

                # Update peak level for auto-gain (slow decay)
                if raw_level > peak_level:
                    peak_level = raw_level
                else:
                    peak_level *= 0.995  # Slow decay
                peak_level = max(peak_level, 0.001)

                # Normalize against peak (auto-gain)
                normalized_level = min(1.0, raw_level / peak_level)

                # Smooth the level to prevent flicker
                smoothed_level = prev_level * smoothing + normalized_level * (1.0 - smoothing)
                prev_level = smoothed_level

                # Map intensity to hue (blue → green → red → magenta)
                hue = _intensity_to_hue(smoothed_level)

                # Saturation: higher when level is higher
                saturation = 0.6 + smoothed_level * 0.4

                # Value (brightness in HSV): scales with level
                # Use a sharper curve for more pronounced blinking
                value = 0.03 + (smoothed_level ** 1.5) * 0.97

                r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
                r, g, b = int(r * 255), int(g * 255), int(b * 255)
                color = (_clamp(r), _clamp(g), _clamp(b))

                # Smooth color transitions
                color = _smooth_color(prev_color, color, 1.0 - smoothing)
                prev_color = color

                # Keyboard brightness also pulses with the beat
                beat_brightness = int(brightness * (0.1 + smoothed_level * 0.9))
                beat_brightness = _clamp(beat_brightness, 5, 100)

                # Set ALL zones to the same color — entire keyboard reacts as one
                _write_all_zones([color] * NUM_ZONES, beat_brightness)

            except IOError:
                # Buffer overflow or underflow — skip this frame
                continue

    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()
        print("\n🎵 Music visualizer stopped.")


# =============================================================================
# Interactive Menu
# =============================================================================
def _get_color_input(prompt="Enter RGB color (e.g., 255 0 128)", default=(255, 255, 255)):
    """Get an RGB color from user input."""
    raw = input(f"{prompt}\nJust press Enter for default {default}: ").strip()
    if not raw:
        return default
    try:
        parts = [int(x) for x in raw.split() if x]
        if len(parts) != 3 or not all(0 <= v <= 255 for v in parts):
            print("Invalid color. Using default.")
            return default
        return tuple(parts)
    except ValueError:
        print("Invalid input. Using default.")
        return default


def _get_speed_input(default=0.05):
    """Get animation speed from user input."""
    raw = input(
        f"Enter animation speed (seconds per frame, lower = faster)\n"
        f"Recommended: 0.03 (fast) to 0.15 (slow)\n"
        f"Just press Enter for default ({default}): "
    ).strip()
    if not raw:
        return default
    try:
        val = float(raw)
        if val <= 0:
            print("Speed must be positive. Using default.")
            return default
        return val
    except ValueError:
        print("Invalid input. Using default.")
        return default


def _get_brightness_input(default=100):
    """Get brightness from user input."""
    raw = input(
        f"Enter brightness (0-100)\nJust press Enter for default ({default}): "
    ).strip()
    if not raw:
        return default
    try:
        val = int(raw)
        if val < 0 or val > 100:
            print("Brightness must be 0-100. Using default.")
            return default
        return val
    except ValueError:
        print("Invalid input. Using default.")
        return default


def interactive_menu():
    """Run the interactive software modes menu."""
    os.system("clear")
    print("=" * 55)
    print("  ✦  Acer Predator — Software RGB Modes  ✦")
    print("=" * 55)
    print()
    print("  These modes are software-driven animations that")
    print("  cycle the hardware modes from Python.")
    print()
    print("  1. 🌈  Rainbow Cycle")
    print("  2. ⚡  Color Strobe / Flash")
    print("  3. 🚨  Police Siren")
    print("  4. 🔥  Campfire")
    print("  5. ✨  Random Sparkle")
    print("  6. 🎨  Gradient Sweep")
    print("  7. 🌊  Dual-Color Wave")
    print("  8. 💫  Custom Pulse")
    print("  9. 🖥️   Ambient Display (Screen → Keyboard)")
    print(" 10. 🎵  Ambient Music Visualizer")
    print("  0.     Exit")
    print()

    try:
        choice = int(input("  Enter your choice: "))
    except ValueError:
        print("Invalid choice.")
        sleep(1)
        interactive_menu()
        return

    os.system("clear")

    if choice == 1:
        spd = _get_speed_input(0.05)
        brt = _get_brightness_input()
        rainbow_cycle(speed=spd, brightness=brt)

    elif choice == 2:
        color = _get_color_input("Enter strobe color (e.g., 255 0 255)")
        freq = _get_speed_input(0.1)
        brt = _get_brightness_input()
        color_strobe(red=color[0], green=color[1], blue=color[2],
                     frequency=freq, brightness=brt)

    elif choice == 3:
        spd = _get_speed_input(0.15)
        brt = _get_brightness_input()
        police_siren(speed=spd, brightness=brt)

    elif choice == 4:
        spd = _get_speed_input(0.08)
        brt = _get_brightness_input()
        campfire(speed=spd, brightness=brt)

    elif choice == 5:
        spd = _get_speed_input(0.06)
        brt = _get_brightness_input()
        random_sparkle(speed=spd, brightness=brt)

    elif choice == 6:
        c1 = _get_color_input("Enter start color (e.g., 255 0 0)", (255, 0, 0))
        c2 = _get_color_input("Enter end color (e.g., 0 0 255)", (0, 0, 255))
        spd = _get_speed_input(0.05)
        brt = _get_brightness_input()
        gradient_sweep(color1=c1, color2=c2, speed=spd, brightness=brt)

    elif choice == 7:
        c1 = _get_color_input("Enter first wave color (e.g., 255 0 0)", (255, 0, 0))
        c2 = _get_color_input("Enter second wave color (e.g., 0 255 0)", (0, 255, 0))
        spd = _get_speed_input(0.1)
        brt = _get_brightness_input()
        dual_color_wave(color1=c1, color2=c2, speed=spd, brightness=brt)

    elif choice == 8:
        color = _get_color_input("Enter pulse color (e.g., 0 255 255)", (0, 255, 255))
        spd = _get_speed_input(0.03)
        brt = _get_brightness_input()
        custom_pulse(red=color[0], green=color[1], blue=color[2],
                     speed=spd, brightness=brt)

    elif choice == 9:
        print("Which part of the screen should the keyboard reflect?")
        print("  1. Bottom 40% (recommended — closest to keyboard)")
        print("  2. Full screen")
        print("  3. Top 40%")
        try:
            region_choice = int(input("  Choice [1]: ") or "1")
        except ValueError:
            region_choice = 1
        region_map = {1: "bottom", 2: "full", 3: "top"}
        region = region_map.get(region_choice, "bottom")
        sat = 1.5
        sat_raw = input(
            "Saturation boost (1.0 = natural, 1.5 = vivid, 2.0 = intense)\n"
            "Just press Enter for default (1.5): "
        ).strip()
        if sat_raw:
            try:
                sat = float(sat_raw)
            except ValueError:
                sat = 1.5
        spd = _get_speed_input(0.05)
        brt = _get_brightness_input()
        ambient_display(speed=spd, brightness=brt, sample_region=region,
                        saturation_boost=sat)

    elif choice == 10:
        print("🎵 Ambient Music Visualizer")
        print("   Reacts to your system audio output in real-time!")
        print("   The entire keyboard lights up and blinks as one")
        print("   in sync with the music beat.")
        print("   Color shifts: Blue (calm) → Green → Red/Magenta (intense)")
        print()
        print("   Requirements: pip3 install numpy pyaudio")
        print("   Also needs: sudo apt install portaudio19-dev")
        print()
        # Sensitivity
        sens = 1.5
        sens_raw = input(
            "Sensitivity (how reactive to audio)\n"
            "  0.5 = subtle, 1.5 = balanced, 3.0 = intense\n"
            "Just press Enter for default (1.5): "
        ).strip()
        if sens_raw:
            try:
                sens = float(sens_raw)
                sens = max(0.1, min(5.0, sens))
            except ValueError:
                sens = 1.5
        # Smoothing
        smooth = 0.4
        smooth_raw = input(
            "Smoothing (transition smoothness)\n"
            "  0.1 = snappy/raw, 0.4 = balanced, 0.8 = smooth/mellow\n"
            "Just press Enter for default (0.4): "
        ).strip()
        if smooth_raw:
            try:
                smooth = float(smooth_raw)
                smooth = max(0.0, min(0.95, smooth))
            except ValueError:
                smooth = 0.4
        brt = _get_brightness_input()
        music_visualizer(sensitivity=sens, brightness=brt, smoothing=smooth)

    elif choice == 0:
        print("Exiting.")
        sys.exit(0)

    else:
        print("Invalid choice.")
        sleep(1)
        interactive_menu()


if __name__ == "__main__":
    interactive_menu()
