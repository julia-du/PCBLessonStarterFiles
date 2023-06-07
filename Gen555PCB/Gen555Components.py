from edg import *


# Through-Hole LED Footprint
class ThtLed(Led, FootprintBlock):
    def contents(self):
        super().contents()
        self.footprint('D', 'LED_THT:LED_D5.0mm',
                       {
                           '1': self.k,
                           '2': self.a
                       },
                       part='LED')


# Through-Hole Power Connector Footprint
class ThtPower(PowerBarrelJack, FootprintBlock):
    def contents(self):
        super().contents()
        self.footprint('J', 'TestPoint:TestPoint_2Pads_Pitch5.08mm_Drill1.3mm',
                       {
                           '1': self.gnd,
                           '2': self.pwr
                       })


# Through-Hole Switch Footprint
class ThtSwitch(TactileSwitch, FootprintBlock):
    def contents(self):
        super().contents()

        self.footprint('SW', 'Button_Switch_THT:SW_PUSH_6mm',
                       {
                           '1': self.a,
                           '2': self.b
                       },
                       part='6x6mm Switch')


# NE555 Device
class NE555P(FootprintBlock):
    def __init__(self) -> None:
        super().__init__()

        self.vcc = self.Port(VoltageSink(voltage_limits=(4.5, 16) * Volt, current_draw=(2, 15) * mAmp))
        self.gnd = self.Port(Ground())

        self.trig = self.Port(Passive())
        self.cont = self.Port(Passive())
        self.thres = self.Port(Passive())
        self.disch = self.Port(Passive())

        self.reset = self.Port(VoltageSink())
        self.out = self.Port(DigitalSource.from_supply(self.gnd, self.vcc, current_limits=(-200, 200) * mAmp))

    def contents(self) -> None:
        super().contents()
        self.footprint(
            'U', 'Package_DIP:DIP-8_W7.62mm',
            {
                '1': self.gnd,
                '2': self.trig,
                '3': self.out,
                '4': self.reset,
                '5': self.cont,
                '6': self.thres,
                '7': self.disch,
                '8': self.vcc,
            },
            mfr='Texas Instruments', part='NE555P',
            datasheet='https://www.ti.com/lit/ds/symlink/ne555.pdf'
        )


# Astable 555 Timer w/ Calculation
class Astable555Timer(GeneratorBlock):
    @init_in_parent
    def __init__(self, freq: FloatLike, duty: FloatLike, rA_desired: FloatLike) -> None:
        super().__init__()
        self.ne = self.Block(NE555P())

        # Exporting Ports
        self.gnd = self.Export(self.ne.gnd)
        self.pwr = self.Export(self.ne.vcc)
        self.out = self.Export(self.ne.out)
        self.reset = self.Export(self.ne.reset)

        self.actual_freq = self.Parameter(RangeExpr())
        self.actual_duty = self.Parameter(RangeExpr())

        # Set up generator
        self.freq = self.ArgParameter(freq)
        self.duty = self.ArgParameter(duty)
        self.rA_desired = self.ArgParameter(rA_desired)
        self.generator_param(self.freq, self.duty, self.rA_desired)

    def generate(self) -> None:
        super().generate()

        # Cont Pin Decoupling Cap
        self.capContBypass = self.Block(Capacitor(capacitance=0.1 * uFarad(tol=0.10), voltage=25 * Volt(tol=0.20)))

        # Maximum Resistance
        iThres = 250E-9
        rA_max = (2-1/self.get(self.duty))*self.pwr.link().voltage.lower()/(3*iThres)
        rA_target = rA_max.min(self.get(self.rA_desired))

        # Timing Resistors/Caps
        tol = 0.05
        self.rA = self.Block(Resistor(resistance=((1-tol)*rA_target, (1+tol)*rA_target)))
        # FloatExpr doesn't work with * Ohm(tol = 0.05)

        rB_target = ((1-self.get(self.duty))/(2*self.get(self.duty)-1)) * self.rA.actual_resistance
        self.rB = self.Block(Resistor(resistance=((1-tol)*rB_target.lower(), (1+tol)*rB_target.upper())))

        cap_target = 1 / (self.get(self.freq) * 0.693 * (self.rA.actual_resistance + 2 * self.rB.actual_resistance))
        self.cap = self.Block(Capacitor(capacitance=((1-tol)*cap_target.lower(), (1+tol)*cap_target.upper()), voltage=25 * Volt(tol=0.20)))

        self.assign(self.actual_freq, 1 / (self.cap.actual_capacitance * 0.693 * (self.rA.actual_resistance + 2 * self.rB.actual_resistance)))
        self.assign(self.actual_duty, 1 - (self.rA.actual_resistance/(self.rA.actual_resistance + 2*self.rB.actual_resistance)))

        # Vcc Decoupling Cap
        self.capBypass = self.Block(Capacitor(capacitance=0.1 * uFarad(tol=0.10), voltage=25 * Volt(tol=0.20)))

        # Resistor/Cap Connections
        self.VCC = self.connect(self.pwr, self.rA.a.adapt_to(VoltageSink()), self.capBypass.pos.adapt_to(VoltageSink()))
        self.GND = self.connect(self.gnd, self.cap.neg.adapt_to(Ground()), self.capBypass.neg.adapt_to(Ground()), self.capContBypass.neg.adapt_to(Ground()))
        self.CONT = self.connect(self.ne.cont, self.capContBypass.pos)
        self.DIS = self.connect(self.rA.b, self.rB.a, self.ne.disch)
        self.THR = self.connect(self.rB.b, self.ne.trig, self.ne.thres, self.cap.pos)

    def contents(self) -> None:
        super().contents()
