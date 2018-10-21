BUILD_DIR = build
PCAP_DIR = pcaps
LOG_DIR = logs

TOPO = topology.json
P4C = p4c-bm2-ss
RUN_SCRIPT = ../../utils/run_exercise.py

source := $(wildcard *.p4)
outfile := $(source:.p4=.json)

compiled_json := $(BUILD_DIR)/$(outfile)

# Define NO_P4 to start BMv2 without a program
ifndef NO_P4
run_args += -j $(compiled_json)
endif

# Set BMV2_SWITCH_EXE to override the BMv2 target
ifdef BMV2_SWITCH_EXE
run_args += -b $(BMV2_SWITCH_EXE)
endif

all: run

run: build
	sudo python $(RUN_SCRIPT) -t $(TOPO) $(run_args)

stop:
	sudo mn -c

build: dirs
	p4c-bm2-ss --p4v 16 --p4runtime-file build/advanced_tunnel.p4info --p4runtime-format text -o build/advanced_tunnel.json advanced_tunnel.p4
	p4c-bm2-ss --p4v 16 --p4runtime-file build/mri.p4info --p4runtime-format text -o build/mri.json mri.p4

dirs:
	mkdir -p $(BUILD_DIR) $(PCAP_DIR) $(LOG_DIR)

clean: stop
	rm -f *.pcap
	rm -rf $(BUILD_DIR) $(PCAP_DIR) $(LOG_DIR)
