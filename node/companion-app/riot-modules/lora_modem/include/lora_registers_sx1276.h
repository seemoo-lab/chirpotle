#ifndef LORA_REGISTERS_SX1276_H
#define LORA_REGISTERS_SX1276_H

// From the Semtech SX1276/77/78/79 datasheet, chapter 6.1, table 41
#define REG1276_FSK_BITRATEMSB                        0x02
#define REG1276_FSK_BITRATELSB                        0x03
#define REG1276_FSK_FDEVMSB                           0x04
#define REG1276_FSK_FDEVLSB                           0x05
#define REG1276_FSK_RXCONFIG                          0x0D
#define REG1276_FSK_RSSICONFIG                        0x0E
#define REG1276_FSK_RSSICOLLISION                     0x0F
#define REG1276_FSK_RSSITHRESH                        0x10
#define REG1276_FSK_RSSIVALUE                         0x11
#define REG1276_FSK_RXBW                              0x12
#define REG1276_FSK_AFCBW                             0x13
#define REG1276_FSK_OOKPEAK                           0x14
#define REG1276_FSK_OOKFIX                            0x15
#define REG1276_FSK_OOKAVG                            0x16
#define REG1276_FSK_AFCFEI                            0x1A
#define REG1276_FSK_AFCMSB                            0x1B
#define REG1276_FSK_AFCLSB                            0x1C
#define REG1276_LORA_HOPCHANNEL                       0x1C
#define REG1276_FSK_FEIMSB                            0x1D
#define REG1276_FSK_FEILSB                            0x1E
#define REG1276_FSK_PREAMBLEDETECT                    0x1F
#define REG1276_LORA_SYMBTIMEOUTLSB                   0x1F
#define REG1276_FSK_RXTIMEOUT1                        0x20
#define REG1276_FSK_RXTIMEOUT2                        0x21
#define REG1276_FSK_RXTIMEOUT3                        0x22
#define REG1276_FSK_RXDELAY                           0x23
#define REG1276_FSK_OSC                               0x24
#define REG1276_FSK_PREAMBLEMSB                       0x25
#define REG1276_FSK_PREAMBLELSB                       0x26
#define REG1276_LORA_MODEMCONFIG3                     0x26
#define REG1276_FSK_SYNCCONFIG                        0x27
#define REG1276_FSK_SYNCVALUE1                        0x28
#define REG1276_LORA_FEIMSB                           0x28
#define REG1276_FSK_SYNCVALUE2                        0x29
#define REG1276_LORA_FEIMID                           0x29
#define REG1276_FSK_SYNCVALUE3                        0x2A
#define REG1276_LORA_FEILSB                           0x2A
#define REG1276_FSK_SYNCVALUE4                        0x2B
#define REG1276_FSK_SYNCVALUE5                        0x2C
#define REG1276_LORA_RSSIWIDEBAND                     0x2C
#define REG1276_FSK_SYNCVALUE6                        0x2D
#define REG1276_FSK_SYNCVALUE7                        0x2E
#define REG1276_FSK_SYNCVALUE8                        0x2F
#define REG1276_FSK_PACKETCONFIG1                     0x30
#define REG1276_FSK_PACKETCONFIG2                     0x31
#define REG1276_LORA_DETECTOPTIMIZE                   0x31
#define REG1276_FSK_PAYLOADLENGTH                     0x32
#define REG1276_FSK_NODEADRS                          0x33
#define REG1276_FSK_BROADCASTADRS                     0x34
#define REG1276_FSK_FIFOTHRESH                        0x35
#define REG1276_FSK_SEQCONFIG1                        0x36
#define REG1276_FSK_SEQCONFIG2                        0x37
#define REG1276_LORA_DETECTIONTHRESHOLD               0x37
#define REG1276_FSK_TIMERRESOL                        0x38
#define REG1276_FSK_TIMER1COEF                        0x39
#define REG1276_FSK_TIMER2COEF                        0x3A
#define REG1276_FSK_IMAGECAL                          0x3B
#define REG1276_FSK_TEMP                              0x3C
#define REG1276_FSK_LOWBATT                           0x3D
#define REG1276_FSK_IRQFLAGS1                         0x3E
#define REG1276_FSK_IRQFLAGS2                         0x3F
#define REG1276_FSK_PLLHOP                            0x44
#define REG1276_TXCO                                  0x4B
#define REG1276_PADAC                                 0x4D
#define REG1276_FORMERTEMP                            0x5B
#define REG1276_FSK_BITRATEFRAC                       0x5D
#define REG1276_AGCREF                                0x61
#define REG1276_AGCTRHESH1                            0x62
#define REG1276_AGCTHRESH2                            0x63
#define REG1276_AGCTRHESH3                            0x64
#define REG1276_PLL                                   0x70

// Register 0x09 (all other is common for both modules)
#define MSK1276_PACONFIG_MAXPOWER                     0x70

// Register 0x1D in LoRa mode (some values are in the common register table)
#define MSK1276_LORA_MODEMCONFIG1_BW                  0xf0
#define VAL1276_LORA_MODEMCONFIG1_BW125               0x70
#define VAL1276_LORA_MODEMCONFIG1_BW250               0x80
#define VAL1276_LORA_MODEMCONFIG1_BW500               0x90
#define MSK1276_LORA_MODEMCONFIG1_CR                  0x0e
#define MSK1276_LORA_MODEMCONFIG1_IMPLICIT_HDR        0x01
#define VAL1276_LORA_MODEMCONFIG1_IMPLICIT_HDR_OFF    0x00
#define VAL1276_LORA_MODEMCONFIG1_IMPLICIT_HDR_ON     0x01

// Register 0x1E in LoRa mode (some values are in the common register table)
#define MSK1276_LORA_MODEMCONFIG2_RXPAYLOADCRC        0x04
#define VAL1276_LORA_MODEMCONFIG2_RXPAYLOADCRC_ON     0x04
#define VAL1276_LORA_MODEMCONFIG2_RXPAYLOADCRC_OFF    0x00
#define MSK1276_LORA_MODEMCONFIG2_SYMBTIMEOUT         0x03

// Register 0x26 in LoRa mode
#define MSK1276_LORA_MODEMCONFIG3_LOWDATARATEOPTIMIZE     0x08
#define VAL1276_LORA_MODEMCONFIG3_LOWDATARATEOPTIMIZE_ON  0x08
#define VAL1276_LORA_MODEMCONFIG3_LOWDATARATEOPTIMIZE_OFF 0x00
#define MSK1276_LORA_MODEMCONFIG3_AGCAUTOON               0x04

// Register 0x33
#define MSK1276_LORA_INVERTIQ_INVERTIQ                0x40
#define VAL1276_LORA_INVERTIQ_INVERTIQ_DEFAULT        0x00
#define VAL1276_LORA_INVERTIQ_INVERTIQ_INVERTED       0x40

#define MSK1276_DIO_MAPPING1_DIO0                     0xc0
#define MSK1276_DIO_MAPPING1_DIO1                     0x30
#define MSK1276_DIO_MAPPING1_DIO2                     0x0c
#define MSK1276_DIO_MAPPING1_DIO3                     0x03

#define MSK1276_DIO_MAPPING1_DIO4                     0xc0
#define MSK1276_DIO_MAPPING1_DIO5                     0x30

#define VAL1276_VERSION                               0x12

#endif /* LORA_REGISTERS_SX1276_H */