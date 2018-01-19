"""Dump / load Scarlett mixer configuration to / from YAML.

Drives ``amixer`` to query / save the mixer's configuration.
"""
import os
import subprocess
import sys

import yaml


class ScalarValue(object):
    """Hold a single ALSA configuration value
    
    - Include the numeric ALSA ID used to set / get it.
    """
    def __init__(self, value=None):
        self._value = value
        self._num_id = None

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        self._value = new_value


class EnumeratedValue(object):
    """Hold an enumerated ALSA configuration value.
    
    - Include the enumerated list of values allowed, per ALSA.

    - Include the numeric ALSA ID used to set
    """
    def __init__(self):
        self._value = None
        self._num_id = None

    @property
    def value(self):
        value = self._value
        if value is None:
            return "n/a"
        value, items = value
        return items[value][1]

    @value.setter
    def value(self, new_value):
        if self._value is None:
            raise ValueError
        old_value, items = self._value
        for index, item in items:
            if item == new_value:
                self._value = index, items
                break
        else:
            raise ValueError(new_value)


class MatrixEntry(object):
    """Hold one row in the internal Scarlett mixer's "mix" matrx.

    - Includes the source for the row.
    - Includes volumes for each mix allowed by the mixer for the row.
    """
    def __init__(self, num):
        self._num = num
        self._source = EnumeratedValue()
        self._mixes = {}

    @property
    def source(self):
        return self._source.value

    @property
    def mixes(self):
        for key, value in sorted(self._mixes.items()):
            yield key, value


class OutputGain(object):
    """Hold configuration for a single output channel in the mixer.

    - Includes sources for the left and right stereo channels.
    - Includes volume for the channel, and whether it is muted.
    """
    def __init__(self, channel):
        self._channel = channel
        self._muted = ScalarValue(False)
        self._volume = ScalarValue(108)
        self._left_source = EnumeratedValue()
        self._right_source = EnumeratedValue()

    @property
    def left(self):
        return self._left_source.value

    @property
    def right(self):
        return self._right_source.value


class InputCapture(object):
    """Hold configuration for a single input channel in the mixer.

    - Includes the source for the channel.
    """
    def __init__(self, num):
        self._num = num
        self._source = EnumeratedValue()

    @property
    def source(self):
        return self._source.value


class Mixer(object):
    """Represent the configuration of the Scarlett mixer.
    
    - Include support for capturing the configuration from the mixer
      via ``amixer``.
    - Include support for saving the configuration to the mixer
      via ``amixer``.
    - Include support for loading the configuration from a YAML stream.
    - Include support for dumping the configuration to a YAML stream.
    """
    def __init__(self):
        self._internal_validity = ScalarValue()
        self._spdif_validity = ScalarValue()
        self._adat_validity = ScalarValue()
        self._usb_sync = EnumeratedValue()
        self._sample_clock_source = EnumeratedValue()
        self._sample_clock_sync = EnumeratedValue()
        self._master_gain = OutputGain("Master")
        self._matrix_entries = {}  # row index -> MatrixEntry
        self._input_captures = {}  # channel number -> InputCapture
        self._output_gains = {}    # channel number -> OutputGain

    @property
    def master_gain(self):
        return self._master_gain._volume.value, self._master_gain._muted.value

    @property
    def output_gains(self):
        for channel, gain in sorted(self._output_gains.items()):
            yield (
                channel,
                gain._volume.value,
                gain._muted.value,
                gain.left,
                gain.right,
            )

    @property
    def matrix_entries(self):
        for num, entry in sorted(self._matrix_entries.items()):
            yield num, entry.source, entry.mixes

    @property
    def input_captures(self):
        for num, capture in sorted(self._input_captures.items()):
            yield num, capture.source

    def load_controls(self):
        """Load mixer configuration from the Scarlett mixer via ``amixer``.
        """
        for name, num_id in sorted(self._extract_controls()):
            self._parse_control(name, num_id)

    def save_controls(self):
        """Save mixer configuration to the Scarlett mixer via ``amixer``.
        """
        for control in (
            self._usb_sync,
            self._sample_clock_source,
            self._master_gain._volume,
        ):
            self._save_one_control(control._num_id, control.value)
        self._save_one_control(
            control._num_id, self._master_gain._muted.value and 'off' or 'on')
        for _, entry in sorted(self._matrix_entries.items()):
            self._save_one_control(entry._source._num_id, entry._source.value)
            for _, mix in entry.mixes:
                self._save_one_control(mix._num_id, mix._value)
        for _, capture in sorted(self._input_captures.items()):
            self._save_one_control(
                capture._source._num_id, capture._source.value)
        for num, gain in sorted(self._output_gains.items()):
            if gain._muted.value:
                doubled = 'off,off'
            else:
                doubled = 'on,on'
            self._save_one_control(gain._muted._num_id, doubled)
            doubled = '%d,%d' % (gain._volume.value, gain._volume.value)
            self._save_one_control(gain._volume._num_id, doubled)
            self._save_one_control(
                gain._left_source._num_id, gain._left_source.value)
            self._save_one_control(
                gain._right_source._num_id, gain._right_source.value)

    def to_yaml(self, stream):
        volume, muted = self.master_gain
        document = {
            "internal-validity": self._internal_validity.value,
            "spdif-validity": self._spdif_validity.value,
            "adat-validity": self._adat_validity.value,
            "usb-sync-status": self._usb_sync.value,
            "sample-clock-source": self._sample_clock_source.value,
            "sample-sync-status": self._sample_clock_sync.value,
            "master-gain": {
                "volume": volume,
                "muted": muted,
            },
        }
        matrix = document['matrix'] = []

        for num, source, mixes in self.matrix_entries:

            entry = {
                "number": num,
                "source": source,
                "mixes": [],
            }

            for mix, volume in mixes:
                entry["mixes"].append({
                    "name": mix,
                    "volume": volume.value,
                })

            matrix.append(entry)

        captures = document["input-captures"] = []

        for channel, source in self.input_captures:
            captures.append({
                "channel": channel,
                "source": source,
            })

        gains = document["output-gains"] = []

        for channel, volume, muted, left, right in self.output_gains:
            gains.append({
                "channel": channel,
                "volume": volume,
                "muted": muted,
                "left-source": left,
                "right-source": right,
            })

        yaml.dump(
            document, stream, default_flow_style=False, indent=2)

    def from_yaml(self, stream):
        document = yaml.load(stream)
        self._internal_validity._value = document['internal-validity']
        self._spdif_validity._value = document['spdif-validity']
        self._adat_validity._value = document['adat-validity']
        self._usb_sync.value = document['usb-sync-status']
        self._sample_clock_source.value = document['sample-clock-source']
        # Read-only control:
        # self._sample_clock_source.value = document.get('sample-clock-status')
        doc_master_gain = document['master-gain']
        self._master_gain._volume._value = doc_master_gain['volume']
        self._master_gain._muted._value = doc_master_gain['muted']
        for doc_entry in document['matrix']:
            num = doc_entry['number']
            if isinstance(num, int):
                num = '%02d' % num
            entry = self._matrix_entries[num]
            entry._source.value = doc_entry['source']
            for doc_mix in doc_entry['mixes']:
                entry._mixes[doc_mix['name']]._value = doc_mix['volume']
        for doc_capture in document['input-captures']:
            channel = doc_capture['channel']
            if isinstance(channel, int):
                channel = '%02d' % channel
            capture = self._input_captures[channel]
            capture._source.value = doc_capture['source']
        for doc_gain in document['output-gains']:
            channel = doc_gain['channel']
            if isinstance(channel, int):
                channel = '%02d' % channel
            gain = self._output_gains[channel]
            gain._volume._value = doc_gain['volume']
            gain._muted._value = doc_gain['muted']
            gain._left_source.value = doc_gain['left-source'] or 'Off'
            gain._right_source.value = doc_gain['right-source'] or 'Off'

    #
    #   Parsing helpers: convert ALSA name -> corresponding config entry.
    #
    def _parse_control(self, name, num_id):
        # Helper for :meth:`load_controls`.
        if name.startswith("Master Playback"):
            self._parse_master_control(name, num_id)
        elif name.startswith("Master"):
            self._parse_output_gain_control(name, num_id)
        elif name.startswith("Matrix"):
            self._parse_matrix_control(name, num_id)
        elif name.startswith("Input Source"):
            self._parse_input_source_control(name, num_id)
        elif name == "Internal Validity":
            self._internal_validity._value = self._get_boolean(num_id)
            self._internal_validity._num_id = num_id
        elif name == "S/PDIF Validity":
            self._spdif_validity._value = self._get_boolean(num_id)
            self._spdif_validity._num_id = num_id
        elif name == "ADAT Validity":
            self._adat_validity._value = self._get_boolean(num_id)
            self._adat_validity._num_id = num_id
        elif name == "Scarlett 18i20 USB-Sync":
            self._usb_sync._value = self._get_enumerated(num_id)
            self._usb_sync._num_id = num_id
        elif name == "Sample Clock Source":
            self._sample_clock_source._value = self._get_enumerated(num_id)
            self._sample_clock_source._num_id = num_id
        elif name == "Sample Clock Sync Status":
            self._sample_clock_sync._value = self._get_enumerated(num_id)
            self._sample_clock_sync._num_id = num_id
        else:
            raise ValueError(name)

    def _parse_master_control(self, name, num_id):
        if name.endswith("Switch"):
            self._master_gain._muted._value = self._get_boolean(num_id)
            self._master_gain._muted._num_id = num_id
        elif name.endswith("Volume"):
            self._master_gain._volume._value = self._get_integer(num_id)
            self._master_gain._volume._num_id = num_id

    def _parse_matrix_control(self, name, num_id):
        _, num, rest = name.split(" ", 2)
        entry = self._matrix_entries.get(num)

        if entry is None:
            entry = self._matrix_entries[num] = MatrixEntry(num)

        if rest.endswith("Input Playback Route"):
            entry._source._value = self._get_enumerated(num_id)
            entry._source._num_id = num_id
        elif rest.endswith("Playback Volume"):
            _, mix_name, _ = rest.split(" ", 2)
            entry._mixes[mix_name] = ScalarValue(self._get_integer(num_id))
            entry._mixes[mix_name]._num_id = num_id
        else:
            raise ValueError(name)

    def _parse_input_source_control(self, name, num_id):
        _, _, num, _, _ = name.split(" ")
        capture = self._input_captures.get(num)

        if capture is None:
            capture = self._input_captures[num] = InputCapture(num)

        capture._source._value = self._get_enumerated(num_id)
        capture._source._num_id = num_id

    def _parse_output_gain_control(self, name, num_id):
        _, channel, rest = name.split(" ", 2)
        if channel.endswith("L") or channel.endswith("R"):
            channel, side = channel[:-1], channel[-1]
            if not rest.endswith("Source Playback Enum"):
                raise ValueError(name)
        else:
            side = None

        channel = "%02d" % int(channel)
        gain = self._output_gains.get(channel)

        if gain is None:
            gain = self._output_gains[channel] = OutputGain(channel)

        if rest.endswith("Switch"):
            gain._muted._value = self._get_boolean(num_id)
            gain._muted._num_id = num_id
        elif rest.endswith("Volume"):
            gain._volume._value = self._get_integer(num_id)
            gain._volume._num_id = num_id
        elif rest.endswith("Source Playback Enum"):
            if side == 'L':
                source = gain._left_source
            elif side == 'R':
                source = gain._right_source
            else:
                raise ValueError(side)
            source._value = self._get_enumerated(num_id)
            source._num_id = num_id
        else:
            raise ValueError(name)

    #
    #   Helpers driving ``amixer``
    #
    @staticmethod
    def _extract_controls():
        dump = subprocess.check_output(
            ["amixer", "-cUSB", "controls"])
        for line in dump.splitlines():
            num_id, _, name = line.split(b",")
            _, num_id = num_id.split(b"=")
            num_id = int(num_id.decode('ascii'))
            _, name = name.split(b"=") 
            name = name.decode('ascii').strip("'")
            yield name, num_id

    @staticmethod
    def _get_boolean(num_id):
        dump = subprocess.check_output(
            ["amixer", "-cUSB", "cget", "numid=%d" % num_id])
        if b"type=BOOLEAN" not in dump:
            raise ValueError("Wrong type")
        lines = dump.splitlines()
        _, value = lines[-1].split(b"=")
        value = value.decode("ascii")
        if "," in value:
            value, _ = value.split(",", 1)
        return value in ("1", "on")

    @staticmethod
    def _get_integer(num_id):
        dump = subprocess.check_output(
            ["amixer", "-cUSB", "cget", "numid=%d" % num_id])
        if b"type=INTEGER" not in dump:
            raise ValueError("Wrong type")
        for line in dump.splitlines():
            if line.startswith(b"  : values="):
                _, value = line.split(b"=")
                value = value.decode("ascii")
                if "," in value:
                    value, _ = value.split(",")
                return int(value)
        raise ValueError("No value")

    @staticmethod
    def _get_enumerated(num_id):
        dump = subprocess.check_output(
            ["amixer", "-cUSB", "cget", "numid=%d" % num_id])
        if b"type=ENUMERATED" not in dump:
            raise ValueError("Wrong type")
        items = []
        for line in dump.splitlines():
            if line.startswith(b"  ; Item #"):
                _, rest = line.split(b"#")
                num, name = rest.split(b" ", 1)
                num = int(num.decode("ascii"))
                name = name.decode("ascii").strip("'")
                items.append((num, name))
            elif line.startswith(b"  : values="):
                _, value = line.split(b"=")
                value = value.decode("ascii")
                return int(value), items
        raise ValueError("No value")

    @staticmethod
    def _save_one_control(num_id, value):
        subprocess.check_output(
            ["amixer", "-cUSB", "cset", "numid=%d" % num_id, "%s" % value])

def main():
    mixer = Mixer()
    mixer.load_controls()  # prepopulates enums, even for loading.

    if len(sys.argv) > 1 and sys.argv[1] == 'load':
        with open(sys.argv[2]) as file:
            mixer.from_yaml(file)
        mixer.save_controls()
    else:
        mixer.to_yaml(sys.stdout)

if __name__ == '__main__':
    main()
