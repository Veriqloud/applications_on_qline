Every program has it's own configuration files. To simplify deployment, `gen_config` can generate all the config files from a single `meta_config.json`.


## Installation

```.bash
cargo build --release
cp target/release/gen_config ~/bin/
```

## Example

For real hardware

```.bash
gen_config -c meta_config_for_real.json
```

For simulator 

```.bash
gen_config -c meta_config_for_sim.json -s sim_config.json
```




