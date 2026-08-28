use clap::Parser;
//use serde::{Deserialize, Serialize};
//use simulator_configs::Configuration;
//use std::default::Default;
use std::path::PathBuf;

use gen_config::config;

#[derive(Parser, Debug)]
struct Cli {
    /// Path to the config file
    #[arg(short = 'c', long)]
    config_path: PathBuf,
    /// Path to hw_sim.json; Simulator only
    #[arg(short = 's', long)]
    sim: Option<PathBuf>,
}



fn main() {
    let cli = Cli::parse();

    // create alice and bob direcotry
    std::fs::create_dir_all("alice").expect("creating directory for alice");
    std::fs::create_dir_all("bob").expect("creating directory for bob");

    // read master config
    let config = config::Config::from_pathbuf(&cli.config_path);

    // for the simulator
    // - gen sim conf
    // - put alice and bob into the file names
    // for the hardware, use the same config for alice and bob
    let mut for_sim = false;
    let (config_alice, config_bob) = match cli.sim {
        Some(sim_path) => {
            for_sim = true;
            let config_alice = config.append_extension("_alice");
            let config_bob = config.append_extension("_bob");
            config::write_sim_config(&config_alice, &config_bob, sim_path);
            (config_alice, config_bob)
        }
        None => {
            (config.clone(), config.clone())
        }
    };
    
    config::write_gc_config_alice(&config_alice, for_sim);
    config::write_gc_config_bob(&config_bob, for_sim);

    config::write_qber_config_alice(&config_alice);
    config::write_qber_config_bob(&config_bob);

    config::write_kms_config(&config_alice, &config_bob);
    config::write_node_config(&config_alice, &config_bob);
    
    config::write_network_alice(&config);
    config::write_network_bob(&config);




}



