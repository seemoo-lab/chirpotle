.PHONY: all
all: figure01.pdf figure02.pdf figure03.pdf figure04.pdf figure05.pdf figure06.pdf figure07.pdf figure08.pdf figure09.pdf figure10.pdf figure11.pdf figure12.pdf figure13.pdf figure14.pdf table01.pdf table02.pdf table03.pdf

%.pdf:: %.tex
	latexmk -g -pdf $<

# Figure from channel baseline:
figure08.pdf:: ../channel-baseline/data/channel-aggregated-freq.csv

../channel-baseline/data/channel-aggregated-freq.csv: ../channel-baseline/results/channel-baseline-wisec2020.tar.xz
	cd ../channel-baseline; ./process-paper-results.sh 

# Figures/Tables related to ADR spoofing:
figure05.pdf:: ../adr-spoofing/data/frame-transmission-time.csv

figure10.pdf:: ../adr-spoofing/data/adr_trig.csv

figure11.pdf:: ../adr-spoofing/data/timing_info_rx2.csv

table02.pdf:: ../adr-spoofing/data/adr_rampup_aggregated.csv

../adr-spoofing/data/frame-transmission-time.csv ../adr-spoofing/data/adr_trig.csv ../adr-spoofing/data/timing_info_rx2.csv ../adr-spoofing/data/adr_rampup_aggregated.csv: ../adr-spoofing/logs/adr-wormhole-wisec2020.tar.xz ../adr-spoofing/results/adr-wormhole-wisec2020.tar.xz
	cd ../adr-spoofing; ./process-paper-results.sh

# Figures from beacon spoofing:
figure12.pdf: ../beacon-spoofing/data/downlink-availability.csv

figure13.pdf: ../beacon-spoofing/data/beacon-status.csv

figure14.pdf: ../beacon-spoofing/data/beacon-status.csv

table03.pdf:: ../beacon-spoofing/data/beacon-eval-params.csv

../beacon-spoofing/data/downlink-availability.csv ../beacon-spoofing/data/beacon-status.csv ../beacon-spoofing/data/beacon-eval-params.csv: ../beacon-spoofing/logs/beacon-spoofing-wisec2020.tar.xz ../beacon-spoofing/results/beacon-spoofing-wisec2020.tar.xz
	cd ../beacon-spoofing; ./process-paper-results.sh

# Figures/Tables not realted to any testing:
# - table01

# Cleaning:
.PHONY: clean-intermediates
clean-intermediates:
	@rm -f *.log *.fls *.fdb_latexmk *.aux

.PHONY: clean-data
clean-data:
	@rm -f ../adr-spoofing/results/*.json
	@rm -f ../adr-spoofing/logs/*.log
	@rm -f ../adr-spoofing/data/*.csv
	@rm -f ../beacon-spoofing/results/*.json
	@rm -f ../beacon-spoofing/logs/*.log
	@rm -f ../beacon-spoofing/data/*.csv
	@rm -f ../channel-baseline/data/*.csv
	@rm -f ../channel-baseline/results/channel_baseline.log ../channel-baseline/results/channel_baseline.json

.PHONY: clean
clean: clean-intermediates
	@rm -f *.pdf
