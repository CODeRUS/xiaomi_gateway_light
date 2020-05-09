"""
Used code from:

https://community.home-assistant.io/t/light-fade-in/35509
https://github.com/home-assistant/example-custom-config/blob/master/custom_components/example_light/light.py
https://github.com/rytilahti/python-miio/blob/master/miio/gateway.py
"""

import logging
import math
import time

import voluptuous as vol

from miio import Device
from miio.utils import brightness_and_color_to_int, int_to_brightness, int_to_rgb

import homeassistant.helpers.config_validation as cv
# Import the device class from the component that you want to support
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION ,
    PLATFORM_SCHEMA,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR,
    SUPPORT_TRANSITION,
    Light
)
from homeassistant.const import CONF_HOST, CONF_TOKEN
import homeassistant.util.color as color_util

_LOGGER = logging.getLogger(__name__)

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_TOKEN): cv.string,
})

SUPPORT_GATEWAY_LIGHT = (
    SUPPORT_BRIGHTNESS | SUPPORT_COLOR | SUPPORT_TRANSITION
)

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Awesome Light platform."""
    # Assign configuration variables.
    # The configuration check takes care they are present.
    host = config[CONF_HOST]
    token = config[CONF_TOKEN]

    # Setup connection with device
    gateway = Device(host, token)
    # Verify that passed in configuration works
    try:
        info = gateway.send("miIO.info")
        _LOGGER.debug("Connected to Xiaomi Gateway device %s", info["model"])
    except:
        _LOGGER.error("Could not connect to Xiaomi Gateway device")
        return

    # Add devices
    devices = []
    devices.append(GatewayLight(gateway, info))

    add_entities(devices)


color_map = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "white": (255, 255, 255),
    "yellow": (255, 255, 0),
    "orange": (255, 165, 0),
    "aqua": (0, 255, 255),
    "olive": (128, 128, 0),
    "purple": (128, 0, 128),
}


class GatewayLight(Light):
    def __init__(self, device, info):
        self._gateway = device
        self._info = info

        self._name = 'xiaomi_gateway_' + self._gateway.ip
        self._state = None
        self._brightness = None
        self._color = None
        self._hs = None

        _LOGGER.debug("Xiaomi Gateway name is %s", self._name)

    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def supported_features(self):
        """Flag supported features."""
        return SUPPORT_GATEWAY_LIGHT

    @property
    def brightness(self):
        """Return the brightness of the light.
        This method is optional. Removing it indicates to Home Assistant
        that brightness is not supported for this light.
        """
        return self._brightness

    @property
    def hs_color(self) -> tuple:
        """Return the color property."""
        return self._hs

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._state

    def set_rgb(self, rgb, transition):
        """Set bulb's color."""
        if rgb and self.supported_features & SUPPORT_COLOR:
            self._color = rgb
            self._hs = color_util.color_RGB_to_hs(*self._color)
            self.set_gateway_color(rgb)

    def set_brightness(self, brightness, transition):
        """Set bulb brightness."""
        if brightness is not None:
            self._brightness = brightness
            self.set_gateway_brightness(brightness, transition)

    def turn_on(self, **kwargs):
        """Instruct the light to turn on.
        You can skip the brightness part if your light does not support
        brightness control.
        """
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._brightness)
        if not brightness:
            brightness = 255
        self._hs = kwargs.get(ATTR_HS_COLOR, self._hs)
        if self._hs:
            self._color = color_util.color_hs_to_RGB(*self._hs)
        else:
            self._color = kwargs.get(ATTR_RGB_COLOR, self._color)
            self._hs = color_util.color_RGB_to_hs(*self._color)
        if brightness == self._brightness:
            self.set_gateway_light(self._color, self._brightness)
        else:
            self.set_gateway_light(self._color, self._brightness)
            self.set_gateway_brightness(brightness, kwargs.get(ATTR_TRANSITION))
            self._brightness = brightness
        self._state = True

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        self.set_gateway_brightness(0, kwargs.get(ATTR_TRANSITION))
        self._state = False

    def update(self):
        """Fetch new state data for this light.
        This is the only method that should fetch new data for Home Assistant.
        """

        rgb = self._gateway.send("get_rgb")[0]

        self._color = int_to_rgb(rgb)
        self._brightness = int(int_to_brightness(rgb) / 100 * 255)
        self._state = self._brightness > 0

    def set_gateway_brightness(self, brightness, transition=None):
        """Set gateway lamp brightness (0-100)."""
        if transition:
            start_level = self._brightness

            """ Use brightness or convert brightness_pct """
            end_level = int(brightness)

            """ Calculate number of steps """
            steps = int(math.fabs((start_level - end_level)))
            fadeout = True if start_level > end_level else False

            """ Calculate the delay time """
            delay = round(transition / steps, 3)

            """ Disable delay anbd increase stepping if delay < 3/4 second """
            if (delay < .750):
                delay = 0
                steps = int(steps / 5)
                step_by = 5
            else:
                step_by = 1

            _LOGGER.info('Setting brightness'
                         ' from ' + str(start_level) + ' to ' + str(end_level) +
                         ' steps ' + str(steps) + ' delay ' + str(delay))

            new_level = start_level
            for x in range(steps):
                current_level = self._brightness
                if (fadeout and current_level < new_level):
                    break
                elif (not fadeout and current_level > new_level):
                    break
                else:
                    self.set_gateway_brightness(new_level)
                    if (fadeout):
                        new_level = new_level - step_by
                    else:
                        new_level = new_level + step_by
                    """ Do not sleep for 0 delay """
                    if (delay > 0):
                        time.sleep(delay)
            if new_level != brightness:
                self.set_gateway_brightness(brightness)
        else:
            brightness_and_color = brightness_and_color_to_int(int(brightness / 255 * 100), self._color)
            return self._gateway.send("set_rgb", [brightness_and_color])

    def set_gateway_light(self, color, brightness):
        """Set color (using color name) and brightness (0-100)."""
        if 100 < brightness < 0:
            brightness = 100
        if color in color_map.keys():
            color = color_map[color]
        brightness_and_color = brightness_and_color_to_int(
            brightness, color
        )
        return self._gateway.send("set_rgb", [brightness_and_color])

    def set_gateway_color(self, color):
        """Set gateway lamp color using color name (red, green, etc)."""
        if color in color_map.keys():
            color = color_map[color]
        current_brightness = int(self._brightness / 255 * 100)
        brightness_and_color = brightness_and_color_to_int(
            current_brightness, color
        )
        return self.send("set_rgb", [brightness_and_color])
