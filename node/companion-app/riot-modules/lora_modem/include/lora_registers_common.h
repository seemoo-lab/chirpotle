#ifndef LORA_REGISTERS_COMMON_H
#define LORA_REGISTERS_COMMON_H
/**
 * Contains common register IDs, values and masks, which can be used for both,
 * the SX1272-compatible and SX1276-compatible transceivers.
 *
 * REG... are register IDs
 * VAL... are values
 * MSK... are masks for bitfields
 */

// From the Semtech SX1272 datasheet, chapter 6.3, table 107
// From the Semtech SX1276/77/78/79 datasheet, chapter 6.1, table 41
#define REG127X_FIFO                                  0x00
#define REG127X_OPMODE                                0x01

#define REG127X_FRFMSB                                0x06
#define REG127X_FRFMID                                0x07
#define REG127X_FRFLSB                                0x08
#define REG127X_PACONFIG                              0x09
#define REG127X_PARAMP                                0x0A
#define REG127X_OCP                                   0x0B
#define REG127X_LNA                                   0x0C
#define REG127X_LORA_FIFOADDRPTR                      0x0D
#define REG127X_LORA_FIFOTXBASEADDR                   0x0E
#define REG127X_LORA_FIFORXBASEADDR                   0x0F
#define REG127X_LORA_RXCURRENTADDR                    0x10
#define REG127X_LORA_IRQFLAGSMASK                     0x11
#define REG127X_LORA_IRQFLAGS                         0x12
#define REG127X_LORA_RXNBBYTES                        0x13
#define REG127X_LORA_RXHEADERCNTVALUEMSB              0x14
#define REG127X_LORA_RXHEADERCNTVALUELSB              0x15
#define REG127X_LORA_RXPACKETCNTVALUEMSB              0x16
#define REG127X_LORA_RXPACKETCNTVALUELSB              0x17
#define REG127X_LORA_MODEMSTAT                        0x18
#define REG127X_LORA_PKTSNRVALUE                      0x19
#define REG127X_LORA_PKTRSSIVALUE                     0x1A
#define REG127X_LORA_RSSIVALUE                        0x1B
#define REG127X_LORA_MODEMCONFIG1                     0x1D
#define REG127X_LORA_MODEMCONFIG2                     0x1E

#define REG127X_LORA_PREAMBLEMSB                      0x20
#define REG127X_LORA_PREAMBLELSB                      0x21
#define REG127X_LORA_PAYLOADLENGTH                    0x22
#define REG127X_LORA_MAXPAYLOADLENGTH                 0x23
#define REG127X_LORA_HOPPERIOD                        0x24
#define REG127X_LORA_FIFORXBYTEADDR                   0x25

#define REG127X_LORA_INVERTIQ                         0x33
#define REG127X_LORA_SYNCWORD                         0x39
#define REG127X_DIO_MAPPING1                          0x40
#define REG127X_DIO_MAPPING2                          0x41

#define REG127X_VERSION                               0x42

// Register 0x01
#define MSK127X_OPMODE_MODULATION                     0x80
#define VAL127X_OPMODE_MODULATION_LORA                0x80
#define VAL127X_OPMODE_MODULATION_FSK                 0x00
#define MSK127X_OPMODE_MODE                           0x07
#define VAL127X_OPMODE_MODE_SLEEP                     0x00
#define VAL127X_OPMODE_MODE_STANDBY                   0x01
#define VAL127X_OPMODE_MODE_FSTX                      0x02
#define VAL127X_OPMODE_MODE_TX                        0x03
#define VAL127X_OPMODE_MODE_FSRX                      0x04
#define VAL127X_OPMODE_MODE_RXCONTINUOUS              0x05
#define VAL127X_OPMODE_MODE_RXSINGLE                  0x06
#define VAL127X_OPMODE_MODE_CAD                       0x07

// Register 0x09
#define MSK127X_PACONFIG_PASELECT                     0x80
#define VAL127X_PACONFIG_PASELECT_RFO                 0x00
#define VAL127X_PACONFIG_PASELECT_PABOOST             0x80
#define MSK127X_PACONFIG_OUTPUTPOWER                  0x0f

// Register 0x0C
#define MSK127X_LNA_GAIN                              0xe0
#define VAL127X_LNA_GAIN_MAX                          0x20
#define VAL127X_LNA_GAIN_MIN                          0xc0
#define MSK127X_LNA_BOOST                             0x03
#define VAL127X_LNA_BOOST_ON                          0x03
#define VAL127X_LNA_BOOST_OFF                         0x00

// Registers 0x11 and 0x12 in LoRa mode
#define VAL127X_LORA_IRQFLAGS_RXTIMEOUT               0x80
#define VAL127X_LORA_IRQFLAGS_RXDONE                  0x40
#define VAL127X_LORA_IRQFLAGS_PAYLOADCRCERROR         0x20
#define VAL127X_LORA_IRQFLAGS_VALIDHEADER             0x10
#define VAL127X_LORA_IRQFLAGS_TXDONE                  0x08
#define VAL127X_LORA_IRQFLAGS_CADDONE                 0x04
#define VAL127X_LORA_IRQFLAGS_FHSSCHANGECHANNEL       0x02
#define VAL127X_LORA_IRQFLAGS_CADDETECTED             0x01

// Register 0x18 in LoRa mode
#define MSK127X_LORA_MODEMSTAT_RXCODINGRATE           0xE0
#define VAL127X_LORA_MODEMSTAT_CLEAR                  0x10
#define VAL127X_LORA_MODEMSTAT_HEADERINFOVALID        0x08
#define VAL127X_LORA_MODEMSTAT_RXACTIVE               0x04
#define VAL127X_LORA_MODEMSTAT_SIGNALSYNCHRONIZED     0x02
#define VAL127X_LORA_MODEMSTAT_SIGNALDETECTED         0x01

// Register 0x1E in LoRa mode (other values are transceiver-specific)
#define MSK127X_LORA_MODEMCONFIG2_SF                  0xf0
#define MSK127X_LORA_MODEMCONFIG2_TXCONTINUOUS        0x08

// Register 0x34 (INVERTIQ)
// These are pseudo values, as SX1272 distinguishes between tx and rx, but this
// flag can be used to _read_ the current state. For writing, see the modem
// specific registers, and also take care of setting 0x3B of the SX1272
#define MSK127X_LORA_INVERTIQ_INVERTIQ                0x40
#define VAL127X_LORA_INVERTIQ_INVERTIQ_DEFAULT        0x00
#define VAL127X_LORA_INVERTIQ_INVERTIQ_INVERTED       0x40

// Register 0x40 (DIO_MAPPING1)
#define MSK127X_DIO_MAPPING1_DIO0                     0xc0
#define VAL127X_DIO_MAPPING1_DIO0_RXDONE              0x00
#define VAL127X_DIO_MAPPING1_DIO0_TXDONE              0x40
#define VAL127X_DIO_MAPPING1_DIO0_CADDETECTED         0x80
#define MSK127X_DIO_MAPPING1_DIO3                     0x03
#define VAL127X_DIO_MAPPING1_DIO3_CADDONE             0x00
#define VAL127X_DIO_MAPPING1_DIO3_VALIDHEADER         0x01
#define VAL127X_DIO_MAPPING1_DIO3_PAYLOADCRCERROR     0x02

// Register 0x5A (sx1272) or 0x4D (sx1276), data structure is the same
#define MSK127X_PADAC_PADAC                           0x07
#define VAL127X_PADAC_PADAC_DEFAULT                   0x00
#define VAL127X_PADAC_PADAC_BOOST                     0x07

#endif