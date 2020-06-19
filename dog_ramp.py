# ~/development/circuit-python/artifacts/mpy-cross-3.x-windows.exe -O9 dog_ramp.py && cp dog_ramp.mpy /cygdrive/d/lib/dog_ramp.mpy && cp code.py /cygdrive/d/code.py
import gc
import time
import adafruit_hcsr04
import board
import neopixel
import analogio

# Constants
DIST_THRESHOLDS = [10, 15, 20, 40, 50] # centimeters
BRIGHTNESSES = [0.05, 0.1, 0.15, 0.2, 0.3] # % of 1.0
DURATIONS = [10, 15, 20, 25, 30] # seconds
DARKNESS_THRESHOLDS = [5, 10, 20, 50, 75] # 0-1023

# Globals
cpx = None
mode_mgr = None
ramp_pixels = None

class Timer:

    def __init__(self, timeout_sec, timeout_cb):
        self.timeout_sec = timeout_sec
        self.timeout_cb = timeout_cb
        self.start_time = None

    def is_active(self):
        return self.start_time is not None

    def start(self):
        self.start_time = time.monotonic()

    def cancel(self):
        self.start_time = None

    def set_timeout(self, val):
        self.timeout_sec = val

    def update(self):
        if self.start_time is None:
            return
        if (time.monotonic() - self.start_time) >= self.timeout_sec:
            self.start_time = None
            self.timeout_cb()

class Btn:

    def __init__(self, btn_name, pressed_cb):
        self.btn_name = btn_name
        self.pressed_cb = pressed_cb
        self.is_pressed = False

    def update(self):
        is_pressed = getattr(cpx, self.btn_name)
        if self.is_pressed and is_pressed:
            #print('1:1')
            pass
        elif self.is_pressed and not is_pressed:
            #print('1:0')
            self.is_pressed = False
            self.pressed_cb()
        elif not self.is_pressed and is_pressed:
            #print('0:1')
            self.is_pressed = True

class Mode:

    def __init__(self,
                 pixel_idx=None, color=None,
                 mode_timed_out_cb=None,
                 levels_cnt=None,
                 level_changed_cb=None):
        self.pixel_idx = pixel_idx
        self.pixel_color = color
        self.mode_timed_out_cb = mode_timed_out_cb
        self.active_level_idx = 0
        self.levels_cnt = levels_cnt
        self.level_changed_cb = level_changed_cb
        self.timer = Timer(5.0, self.timer_timed_out)

    def get_pixel(self):
        if self.pixel_idx is not None:
            return cpx.pixels[self.pixel_idx]
        else:
            return None

    def set_pixel(self, color):
        if self.pixel_idx is not None:
            cpx.pixels[self.pixel_idx] = color

    def get_level_pixel(self):
        if self.active_level_idx is not None:
            return cpx.pixels[9 - self.active_level_idx]
        else:
            return None

    def set_level_pixel(self, color):
        if self.active_level_idx is not None:
            cpx.pixels[9 - self.active_level_idx] = color

    def timer_timed_out(self):
        self.turn_off_pixel()
        self.turn_off_level_pixel()
        if self.mode_timed_out_cb:
            self.mode_timed_out_cb()

    def turn_on_pixel(self):
        if self.get_pixel() is not None:
            self.set_pixel(self.pixel_color)
            cpx.pixels.show()

    def turn_off_pixel(self):
        if self.get_pixel() is not None:
            self.set_pixel((0, 0, 0))
            cpx.pixels.show()

    def turn_on_level_pixel(self):
        if self.get_level_pixel() is not None:
            self.set_level_pixel(self.pixel_color)
            cpx.pixels.show()

    def turn_off_level_pixel(self):
        if self.get_level_pixel() is not None:
            self.set_level_pixel((0, 0, 0))
            cpx.pixels.show()

    def enter(self):
        if self.get_pixel() is None:
            return
        self.turn_on_pixel()
        self.turn_on_level_pixel()
        self.timer.start()

    def exit(self):
        if self.get_pixel() is None:
            return
        self.timer.cancel()
        self.turn_off_level_pixel()
        self.turn_off_pixel()

    def update(self):
        if self.get_pixel() is None:
            return
        self.timer.update()

    def next_level(self):
        if self.get_pixel() is None:
            return
        self.turn_off_level_pixel()
        self.active_level_idx = (self.active_level_idx + 1) % self.levels_cnt
        self.turn_on_level_pixel()
        self.level_changed_cb(self.active_level_idx)
        self.timer.start()

class ModeMgr:
    
    def __init__(self,
                 btm_dist_thresholds_cnt, btm_dist_threshold_level_cb,
                 top_dist_thresholds_cnt, top_dist_threshold_level_cb,
                 brightnesses_cnt, brightness_level_cb,
                 durations_cnt, duration_level_cb,
                 darkness_thresholds_cnt, darkness_threshold_level_cb):
        self.modes = [
            Mode(), # Null mode (no active mode)
            Mode(0, (32, 0, 0), self.mode_timed_out, btm_dist_thresholds_cnt, btm_dist_threshold_level_cb),
            Mode(1, (0, 32, 0), self.mode_timed_out, top_dist_thresholds_cnt, top_dist_threshold_level_cb),
            Mode(2, (0, 0, 32), self.mode_timed_out, brightnesses_cnt, brightness_level_cb),
            Mode(3, (32, 0, 32), self.mode_timed_out, durations_cnt, duration_level_cb),
            Mode(4, (32, 32, 0), self.mode_timed_out, darkness_thresholds_cnt, darkness_threshold_level_cb)
        ]
        self.active_mode_idx = 0
        self.mode_btn = Btn('button_a', self.next_mode)
        self.level_btn = Btn('button_b', self.next_level)

    def get_active_mode(self):
        return self.modes[self.active_mode_idx]

    def next_mode(self):
        #print('btn pressed: next_mode ' + str(time.monotonic()))
        self.get_active_mode().exit()
        self.active_mode_idx = (self.active_mode_idx + 1) % len(self.modes)
        self.get_active_mode().enter()

    def update(self):
        self.mode_btn.update()
        self.level_btn.update()
        self.get_active_mode().update()

    def mode_timed_out(self):
        self.active_mode_idx = 0
        self.get_active_mode().enter()

    def next_level(self):
        self.get_active_mode().next_level()

    def is_active(self):
        return self.active_mode_idx != 0

class RampPixels:

    def __init__(self):
        self.btm_dist_threshold = DIST_THRESHOLDS[0]
        self.top_dist_threshold = DIST_THRESHOLDS[0]
        self.brightness = BRIGHTNESSES[0]
        self.duration = DURATIONS[0]
        self.darkness_threshold = DARKNESS_THRESHOLDS[0]

        self.pixels = neopixel.NeoPixel(board.D10, 74, brightness=self.brightness)
        self.timer = Timer(self.duration, self.turn_off_pixels)
        self.btm_sonar = adafruit_hcsr04.HCSR04(trigger_pin=board.D9, echo_pin=board.D6)
        self.top_sonar = adafruit_hcsr04.HCSR04(trigger_pin=board.D0, echo_pin=board.D1)

        self.pixels.fill((0, 0, 0))
        self.pixels.show()

        # print('btm dist threshold: ' + str(self.btm_dist_threshold))
        # print('top dist threshold: ' + str(self.top_dist_threshold))
        # print('brightness: ' + str(self.brightness))
        # print('duration: ' + str(self.duration))
        # print('darkness threshold: ' + str(self.darkness_threshold))

    def read_sonar(self, sonar):
        try:
            return sonar.distance
        except:
            return None

    def turn_on_pixels(self):
        self.pixels.brightness = self.brightness
        self.pixels.fill((255, 255, 0))
        self.pixels.show()

    def turn_off_pixels(self):
        self.pixels.fill((0, 0, 0))
        self.pixels.show()

    def update(self):
        if not self.timer.is_active():
            darkness_level = cpx.light
            if darkness_level < self.darkness_threshold:
                # print('darkness level: ' + str(darkness_level))
                btm_dist = self.read_sonar(self.btm_sonar)
                top_dist = self.read_sonar(self.top_sonar)
                if ((btm_dist is not None and btm_dist < self.btm_dist_threshold) or
                    (top_dist is not None and top_dist < self.top_dist_threshold)):
                    # print('btm dist: ' + str(btm_dist))
                    # print('top dist: ' + str(top_dist))
                    self.turn_on_pixels()
                    self.timer.start()
        else:
            self.timer.update()

    def set_btm_dist_threshold(self, idx):
        self.btm_dist_threshold = DIST_THRESHOLDS[idx]
        # print(self.btm_dist_threshold)

    def set_top_dist_threshold(self, idx):
        self.top_dist_threshold = DIST_THRESHOLDS[idx]
        # print(self.top_dist_threshold)

    def set_brightness(self, idx):
        self.brightness = BRIGHTNESSES[idx]
        # print(self.brightness)
        if self.timer.is_active():
            self.pixels.brightness = self.brightness

    def set_duration(self, idx):
        self.duration = DURATIONS[idx]
        # print(self.duration)
        self.timer.set_timeout(self.duration)

    def set_darkness_threshold(self, idx):
        self.darkness_threshold = DARKNESS_THRESHOLDS[idx]
        # print(self.darkness_threshold)

    def is_active(self):
        return self.timer.is_active()

def setup(_cpx):
    global cpx, ramp_pixels, mode_mgr

    cpx = _cpx
    ramp_pixels = RampPixels()
    mode_mgr = ModeMgr(
        len(DIST_THRESHOLDS), ramp_pixels.set_btm_dist_threshold,
        len(DIST_THRESHOLDS), ramp_pixels.set_top_dist_threshold,
        len(BRIGHTNESSES), ramp_pixels.set_brightness,
        len(DURATIONS), ramp_pixels.set_duration,
        len(DARKNESS_THRESHOLDS), ramp_pixels.set_darkness_threshold)

def signal_ready():
    for i in range(10):
        cpx.red_led = True
        time.sleep(0.1)
        cpx.red_led = False
        time.sleep(0.1)    

def processing_loop():
    gc.enable()
    while True:
        if not ramp_pixels.is_active():
            mode_mgr.update()
        if not mode_mgr.is_active():
            ramp_pixels.update()
        gc.collect()

def main(_cpx):
    setup(_cpx)
    signal_ready()
    processing_loop()
