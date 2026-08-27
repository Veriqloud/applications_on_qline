# Build gen_config

```.bash
cd gen_config
cargo build --release
cp target/release/gen_config ~/bin/
```

# Use gen_config

`gen_config` will generate the config files for the individual programs from one meta config. An example of the meta config can be found in the folder `gen_config` for the real hardware and for the simulator.

Example folder structure for the generated config files:

```
qline2
├── meta_config.json         # source for the configuration
├── ports_for_localhost.json # for connection through the internet
├── alice                    # files to be copied over to alice:~/qline/config/
│   ├── network.json
│   ├── gc.json
│   ├── qber.json
│   ├── kms.json
│   └── node.json
└── bob                      # files to be copied over to bob:~/qline/config/
│   ├── network.json
│   ├── gc.json
│   ├── qber.json
│   ├── kms.json
│   └── node.json
```

to generate the remote files run `gen_config` with the appropriate arguments. 

Example (assuming `gen_config` is globally known):

```.bash
cd qline2
gen_config -c meta_config.json
```


For the simulator

```.bash
cd sim
gen_config -c meta_config.json -s sim_config.json
```


