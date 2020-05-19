# Replicability

Use the `Makefile` to re-create the figures from the data measured during the experiments.
If necessary, the postprocessing steps will be executed again before building the figures using LaTeX.
For more details on the postprocessing, have a look at the `process-paper-results.sh` shell script in each of the subdirectories.

```bash
make all # Builds all figures and tables
make figure10.pdf # Builds figure 10
```

See below for lists of figures and tables and their corresponding data sources.

## Figures

| Figure                                     | Title                                             | Data Source                                                          |
| ------------------------------------------ | ------------------------------------------------- | -------------------------------------------------------------------- |
| 01 [pdf](figure01.pdf) [tex](figure01.tex) | Architecture of the ChirpOTLE framework           | static figure                                                        |
| 02 [pdf](figure02.pdf) [tex](figure02.tex) | Control flow in the security evaluation framework | static figure                                                        |
| 03 [pdf](figure03.pdf) [tex](figure03.tex) | Message flow of the unidirectional wormhole       | static figure                                                        |
| 04 [pdf](figure04.pdf) [tex](figure04.tex) | Message flow of the rx2 wormhole                  | static figure                                                        |
| 05 [pdf](figure05.pdf) [tex](figure05.tex) | LoRa frame transmission time                      | LoRa airtime formula, calculated in postprocessing of ADR spoofing   |
| 06 [pdf](figure06.pdf) [tex](figure06.tex) | Message flow of the downlink-delayed wormhole     | static figure                                                        |
| 07 [pdf](figure07.pdf) [tex](figure07.tex) | Concept of the beacon drifting attack             | static figure                                                        |
| 08 [pdf](figure08.pdf) [tex](figure08.tex) | Channel from ED to GW without attacker            | baseline measurements (`channel-aggregated-freq.cv`)                 |
| 09 [pdf](figure09.pdf) [tex](figure09.tex) | Experimental setup                                | static figure                                                        |
| 10 [pdf](figure10.pdf) [tex](figure10.tex) | Trigger for the ED to switch its DR               | ADR spoofing results (`adr_trig.csv`)                                |
| 11 [pdf](figure11.pdf) [tex](figure11.tex) | Measured timing of the rx2 wormhole               | ADR spoofing results (`timing_info_rx2.csv`)                         |
| 12 [pdf](figure12.pdf) [tex](figure12.tex) | Downlink availability during beacon drifting      | Beacon spoofing results (`downlink-availability.csv`)                |
| 13 [pdf](figure13.pdf) [tex](figure13.tex) | Beacon status at ED under attack                  | Beacon spoofing results (`beacon-status.csv`)                        |
| 14 [pdf](figure14.pdf) [tex](figure14.tex) | Beacon SNR during attack                          | Beacon spoofing results (`beacon-status.csv`)                        |

## Tables

| Table                                    | Title                                                                | Data Source                                        |
| ---------------------------------------- | -------------------------------------------------------------------- | -------------------------------------------------- |
| 01 [pdf](table01.pdf) [tex](table01.tex) | Evaluation parameters for the ADR spoofing attack                    | static data                                        |
| 02 [pdf](table02.pdf) [tex](table02.tex) | Number of transactions from start of attack until the DR is adjusted | ADR spoofing results (`adr_rampup_aggregated.csv`) |
| 03 [pdf](table03.pdf) [tex](table03.tex) | Evaluated values for delta t step                                    | Calculated in postprocessing of beacon spoofing    |
