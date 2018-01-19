``scarlett_yaml``
=================

Script for dumping a Focusrite Scarlett's internal mixer configuration
to YAML, and loading it back again.

This is important on Linux for two reasons:

- one cannot run Focusrite's MixControl app (even under Wine or in a
  Windows VM)

- the configuration changes made via ALSA's ``amixer`` are not persisted
  to the interface's flash storage, which means the configuration is
  reset to the factory / last saved values on a power cycle.


Usage
-----

Dump to standard output:

.. code-block: bash

   $ python scarlett_yaml.py

Dump to a file

.. code-block: bash

   $ python scarlett_yaml.py > my_config.yaml

Load from a file:

.. code-block: bash

   $ python scarlett_yaml.py load my_config.yaml


TODOs
-----

- [ ] Normalize command-line handling for the script (e.g., add an
      arg parser, support dumping to a file directly, support loading
      from standard input, etc.)

- [ ] Capture additional ALSA information (e.g., output gain channel names,
      parameter read-write / read-only status, etc.)  See the output of
      ``amixer -cUSB contents``.

- [ ] Extract the data model from the script into a separate, importable
      module.

- [ ] Write some kind of GUI?  Probably YAGNI for me:  the dumped YAML
      is enough for my usecases (I'd rather edit text than use the mouse
      to tweak hundreds of sliders / knobs, e.g. in ``qasmixer``.
