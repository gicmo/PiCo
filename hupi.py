#!/usr/bin/env python
from __future__ import print_function

from time import sleep, time
import threading
from threading import Thread
import RPi.GPIO as GPIO
from huecontroller import HueController
from phue import Bridge
from Queue import Queue
import sys

class Timer(object):
      def __init__(self, duration, callback):
          self.__duration = duration
          self.__callback = callback
          self.__t = time() + self.__duration

      def check(self, now):
          t_over = now - self.__t
          if self.__t > 0 and t_over >= 0:
              #print('Firing timer ', self)
              self.__callback(now)
              self.__t = now + (self.__duration - t_over) #update t for the next firing
          return self.__t

      def dtor(self):
          pass

class Scheduler(object):

    def __init__(self):
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._timer = []
        self._sleep_time = 10

    def put(self, timer):
        self._lock.acquire()
        self._timer.append(timer)
        if len(self._timer) == 1:
            self._cond.notify()

        print ('Timer added: [%d]' % len(self._timer))
        self._lock.release()

    def remove(self, timer):
        self._lock.acquire()
        self._timer.remove(timer)
        timer.dtor()
        print ('Timer removed: [%d]' % len(self._timer))
        self._lock.release()

    @property
    def have_timer(self):
        return len(self._timer)

    def loop(self):
        self._lock.acquire()
        now = time()
        if self.have_timer:
            t_wakeup = min([t.check(now) for t in self._timer])
        else:
            t_wakeup = now + 1.0

        while True:

            while True:
                # if we have events -> timeout at the shortest duration
                #              else -> wait for an event
                sleep_time = t_wakeup - time()
                self._cond.wait(sleep_time)
                if self.have_timer:
                    #print("wakeup")
                    break

            #should only be reached if we have events
            now = time()
            t_wakeup = min([t.check(now) for t in self._timer])

        #end of the loop
        self._lock.release()

class ButtonTimer(Timer):
    def __init__(self, ch_led, callback):
        Timer.__init__(self, 0.1, self._on_timer)
        self._led_chan = ch_led
        self._led_state = 1
        self.toggle_led()
        self._count = 0
        self._callback = callback

    def toggle_led(self):
        self._led_state = not self._led_state
        GPIO.output(self._led_chan, self._led_state)

    def _on_timer(self, now):
        self._callback(now)
        self.toggle_led()
        self._count += 1

    def dtor(self):
        GPIO.output(self._led_chan, 0)


class LightController(threading.Thread):
      def __init__(self, huectl, led, max_delay=0.8):
            Thread.__init__(self)
            self.daemon = True
            self._huectl = huectl
            self._queue = Queue(10)
            self._history = ('R', 0.0, 0)
            self._click_delay = max_delay
            self._lstate = None
            self._led = led

      @property
      def queue(self):
            return self._queue

      def button_down(self, now):
            self.queue.put(('D', now))

      def button_up(self, now):
            self.queue.put(('U', now))

      def toggle(self):
            self.queue.put(('P', time()))

      def hold(self, now):
            self.queue.put(('H', now))

      #internal functions
      def run(self):
            while True:
                  item = self.queue.get()
                  self._process(item)
                  self.queue.task_done()

      def _process(self, item):
            cmd = item[0]
            now = item[1]
            cmd_map = {'D' : self._b_down,
                       'U' : self._b_up,
                       'H' : self._b_hold}
            cmd_func = cmd_map[cmd]
            cmd_func(now)

      def _b_down(self, now):

            self._hstate = (now, 0)
            GPIO.output(self._led, 0)

      def _b_hold(self, now):

            cmd = self._history[0]
            if cmd == 'H':
                  return

            freq = 0.1
            tstart = self._hstate[0]
            count = self._hstate[1] + 1
            self._hstate = (tstart, count)
            button_dt = (time() - now)

            #print('Hold: %s button: %f' % (str(self._hstate), button_dt))

            if button_dt > freq:
                  print('Skipping button press due to delay')
                  return

            delay = now - tstart
            if delay > 2.0:
                  self.check_lights()
                  self._hold_press(self._lstate)
                  self._history = ('H', 0, 0)
                  GPIO.output(self._led, 1)

      def _b_up(self, now):

            cmd, tlast, count = self._history
            if cmd == 'H':
                  #this was the end of a completed hold response,
                  #reset history
                  print('Resetting after hold')
                  self._history = ('R', 0, 0.0)
                  return

            deltat = now - tlast
            print('Delta-T: %f [count: %d]' % (deltat, count))
            if deltat > self._click_delay:
                  count = 0
                  self.check_lights()

            lstate = self._lstate
            if lstate is None:
                  print('WARN: lstate == NONE')
                  GPIO.output(self._led, 1)
                  return

            print ('Light state: %d' % lstate)

            count += 1
            self._history = ('T', now, count)

            self._dispatch_press(lstate, count)
            GPIO.output(self._led, 1)


      def _dispatch_press(self, lstate, count):

            try:
                  if count == 1:
                        self._single_press(lstate)
                  elif count == 2:
                        self._double_press(lstate)
                  elif count == 3:
                        self._tripple_press(lstate)
            except:
                  print('ERROR switching light')


      def _single_press(self, lstate):
            print('Single press')

            if not lstate:
                  # lights are off
                  # switch lights group 1 on
                  self._huectl.set_group(1, 'on', True)
            else:
                  self._huectl.set_group(0, 'on', False)
            self._lstate = not lstate


      def _double_press(self, lstate):
            print('Double press [%d]' % lstate)
            if not lstate:
                  return #light have been turned off -> noop
            print('Loading all state')
            self._huectl.set_group(2, 'on', True)

      def _tripple_press(self, lstate):
            print('Tripple press [%d]' % lstate)
            if not lstate:
                  return #light have been turned off -> noop

      def _hold_press(self, lstate):
            if lstate:
                  g2_state = self._huectl.get_group(2, 'on')
                  self._huectl.set_group(2, 'on', not g2_state)

      def check_lights(self):
            ison = None
            try:
                  ison = self._huectl.get_group(1, 'on')
            except:
                  print('Error fetching Light state')
                  print(sys.exc_info()[0])
            self._lstate = ison


      def check_lights_old(self):
        print('Checking Lights (old)...')

        try:
              lstatus = map(lambda light: light.on, self._huectl.lights)
              ison = reduce(lambda x,y: x or y, lstatus)
        except:
              print('Error fetching Light state')
              ison = None

        self._lstate = ison


class Hupi(object):
    def __init__(self):
        channel = 24

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        self._huectl = Bridge()
        GPIO.setup(channel, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.add_event_detect(channel, GPIO.FALLING | GPIO.RISING, callback = lambda ch: self.on_button(ch),  bouncetime=50)
        self._sched = Scheduler()
        self._blue = 18
        self._green = 23
        GPIO.setup(self._blue, GPIO.OUT)
        GPIO.setup(self._green, GPIO.OUT)
        GPIO.output(self._blue, 1)
        GPIO.output(self._green, 0)
        self._btn_state = 1
        self._lctl = LightController(self._huectl, self._blue)
        self._lctl.start()

    def on_button(self, channel):
        state = not self._btn_state
        self._btn_state = state
        print("state: %d" % state)
        now = time()
        if state == 0:
            self._lctl.button_down(now)
            self._button_timer = ButtonTimer(self._green, self.on_timer)
            self._sched.put(self._button_timer)
        else:
            self._sched.remove(self._button_timer)
            self._lctl.button_up(now)

    def toggle_lights(self):
        self._lctl.toggle()

    def on_timer(self, now):
        self._lctl.hold(now)

    def run(self):
        self._sched.loop()

    def cleanup(self):
        GPIO.output(self._blue, 0)
        GPIO.output(self._green, 0)
        GPIO.cleanup()

if __name__ == '__main__':
    hupi = Hupi()

    try:
        hupi.run()
    except KeyboardInterrupt as ek:
        print('Shutting down')
    except:
        print('Caught un-caught exception. Heh.')
    finally:
        hupi.cleanup()
