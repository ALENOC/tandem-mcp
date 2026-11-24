import unittest

from inventory import export_rows, restock, total_value, unit_price


class InventoryTest(unittest.TestCase):
    def test_unit_price_small_1(self):
        self.assertEqual(unit_price(10.0, 1), 10.0)

    def test_unit_price_small_2(self):
        self.assertEqual(unit_price(10.0, 2), 10.0)

    def test_unit_price_small_3(self):
        self.assertEqual(unit_price(10.0, 3), 10.0)

    def test_unit_price_small_4(self):
        self.assertEqual(unit_price(10.0, 4), 10.0)

    def test_unit_price_small_5(self):
        self.assertEqual(unit_price(10.0, 5), 10.0)

    def test_unit_price_small_6(self):
        self.assertEqual(unit_price(10.0, 6), 10.0)

    def test_unit_price_small_7(self):
        self.assertEqual(unit_price(10.0, 7), 10.0)

    def test_unit_price_small_8(self):
        self.assertEqual(unit_price(10.0, 8), 10.0)

    def test_unit_price_small_9(self):
        self.assertEqual(unit_price(10.0, 9), 10.0)

    def test_unit_price_mid_10(self):
        self.assertEqual(unit_price(20.0, 10), 19.0)

    def test_unit_price_mid_13(self):
        self.assertEqual(unit_price(20.0, 13), 19.0)

    def test_unit_price_mid_16(self):
        self.assertEqual(unit_price(20.0, 16), 19.0)

    def test_unit_price_mid_19(self):
        self.assertEqual(unit_price(20.0, 19), 19.0)

    def test_unit_price_mid_22(self):
        self.assertEqual(unit_price(20.0, 22), 19.0)

    def test_unit_price_mid_25(self):
        self.assertEqual(unit_price(20.0, 25), 19.0)

    def test_unit_price_mid_28(self):
        self.assertEqual(unit_price(20.0, 28), 19.0)

    def test_unit_price_mid_31(self):
        self.assertEqual(unit_price(20.0, 31), 19.0)

    def test_unit_price_mid_34(self):
        self.assertEqual(unit_price(20.0, 34), 19.0)

    def test_unit_price_mid_37(self):
        self.assertEqual(unit_price(20.0, 37), 19.0)

    def test_unit_price_mid_40(self):
        self.assertEqual(unit_price(20.0, 40), 19.0)

    def test_unit_price_mid_43(self):
        self.assertEqual(unit_price(20.0, 43), 19.0)

    def test_unit_price_mid_46(self):
        self.assertEqual(unit_price(20.0, 46), 19.0)

    def test_unit_price_mid_49(self):
        self.assertEqual(unit_price(20.0, 49), 19.0)

    def test_unit_price_mid_52(self):
        self.assertEqual(unit_price(20.0, 52), 19.0)

    def test_unit_price_mid_55(self):
        self.assertEqual(unit_price(20.0, 55), 19.0)

    def test_unit_price_mid_58(self):
        self.assertEqual(unit_price(20.0, 58), 19.0)

    def test_unit_price_mid_61(self):
        self.assertEqual(unit_price(20.0, 61), 19.0)

    def test_unit_price_mid_64(self):
        self.assertEqual(unit_price(20.0, 64), 19.0)

    def test_unit_price_mid_67(self):
        self.assertEqual(unit_price(20.0, 67), 19.0)

    def test_unit_price_mid_70(self):
        self.assertEqual(unit_price(20.0, 70), 19.0)

    def test_unit_price_mid_73(self):
        self.assertEqual(unit_price(20.0, 73), 19.0)

    def test_unit_price_mid_76(self):
        self.assertEqual(unit_price(20.0, 76), 19.0)

    def test_unit_price_mid_79(self):
        self.assertEqual(unit_price(20.0, 79), 19.0)

    def test_unit_price_mid_82(self):
        self.assertEqual(unit_price(20.0, 82), 19.0)

    def test_unit_price_mid_85(self):
        self.assertEqual(unit_price(20.0, 85), 19.0)

    def test_unit_price_mid_88(self):
        self.assertEqual(unit_price(20.0, 88), 19.0)

    def test_unit_price_mid_91(self):
        self.assertEqual(unit_price(20.0, 91), 19.0)

    def test_unit_price_mid_94(self):
        self.assertEqual(unit_price(20.0, 94), 19.0)

    def test_unit_price_mid_97(self):
        self.assertEqual(unit_price(20.0, 97), 19.0)

    def test_unit_price_bulk_100(self):
        self.assertEqual(unit_price(50.0, 100), 45.0)

    def test_unit_price_bulk_104(self):
        self.assertEqual(unit_price(50.0, 104), 45.0)

    def test_unit_price_bulk_108(self):
        self.assertEqual(unit_price(50.0, 108), 45.0)

    def test_unit_price_bulk_112(self):
        self.assertEqual(unit_price(50.0, 112), 45.0)

    def test_unit_price_bulk_116(self):
        self.assertEqual(unit_price(50.0, 116), 45.0)

    def test_unit_price_bulk_120(self):
        self.assertEqual(unit_price(50.0, 120), 45.0)

    def test_unit_price_bulk_124(self):
        self.assertEqual(unit_price(50.0, 124), 45.0)

    def test_unit_price_bulk_128(self):
        self.assertEqual(unit_price(50.0, 128), 45.0)

    def test_unit_price_bulk_132(self):
        self.assertEqual(unit_price(50.0, 132), 45.0)

    def test_unit_price_bulk_136(self):
        self.assertEqual(unit_price(50.0, 136), 45.0)

    def test_unit_price_bulk_140(self):
        self.assertEqual(unit_price(50.0, 140), 45.0)

    def test_unit_price_bulk_144(self):
        self.assertEqual(unit_price(50.0, 144), 45.0)

    def test_unit_price_bulk_148(self):
        self.assertEqual(unit_price(50.0, 148), 45.0)

    def test_unit_price_bulk_152(self):
        self.assertEqual(unit_price(50.0, 152), 45.0)

    def test_unit_price_bulk_156(self):
        self.assertEqual(unit_price(50.0, 156), 45.0)

    def test_unit_price_bulk_160(self):
        self.assertEqual(unit_price(50.0, 160), 45.0)

    def test_unit_price_bulk_164(self):
        self.assertEqual(unit_price(50.0, 164), 45.0)

    def test_unit_price_bulk_168(self):
        self.assertEqual(unit_price(50.0, 168), 45.0)

    def test_unit_price_bulk_172(self):
        self.assertEqual(unit_price(50.0, 172), 45.0)

    def test_unit_price_bulk_176(self):
        self.assertEqual(unit_price(50.0, 176), 45.0)

    def test_unit_price_bulk_180(self):
        self.assertEqual(unit_price(50.0, 180), 45.0)

    def test_unit_price_bulk_184(self):
        self.assertEqual(unit_price(50.0, 184), 45.0)

    def test_unit_price_bulk_188(self):
        self.assertEqual(unit_price(50.0, 188), 45.0)

    def test_unit_price_bulk_192(self):
        self.assertEqual(unit_price(50.0, 192), 45.0)

    def test_unit_price_bulk_196(self):
        self.assertEqual(unit_price(50.0, 196), 45.0)

    def test_unit_price_bulk_200(self):
        self.assertEqual(unit_price(50.0, 200), 45.0)

    def test_unit_price_bulk_204(self):
        self.assertEqual(unit_price(50.0, 204), 45.0)

    def test_unit_price_bulk_208(self):
        self.assertEqual(unit_price(50.0, 208), 45.0)

    def test_unit_price_bulk_212(self):
        self.assertEqual(unit_price(50.0, 212), 45.0)

    def test_unit_price_bulk_216(self):
        self.assertEqual(unit_price(50.0, 216), 45.0)

    def test_unit_price_bulk_220(self):
        self.assertEqual(unit_price(50.0, 220), 45.0)

    def test_unit_price_bulk_224(self):
        self.assertEqual(unit_price(50.0, 224), 45.0)

    def test_unit_price_bulk_228(self):
        self.assertEqual(unit_price(50.0, 228), 45.0)

    def test_unit_price_bulk_232(self):
        self.assertEqual(unit_price(50.0, 232), 45.0)

    def test_unit_price_bulk_236(self):
        self.assertEqual(unit_price(50.0, 236), 45.0)

    def test_unit_price_bulk_240(self):
        self.assertEqual(unit_price(50.0, 240), 45.0)

    def test_unit_price_bulk_244(self):
        self.assertEqual(unit_price(50.0, 244), 45.0)

    def test_unit_price_bulk_248(self):
        self.assertEqual(unit_price(50.0, 248), 45.0)

    def test_unit_price_bulk_252(self):
        self.assertEqual(unit_price(50.0, 252), 45.0)

    def test_unit_price_bulk_256(self):
        self.assertEqual(unit_price(50.0, 256), 45.0)

    def test_unit_price_bulk_260(self):
        self.assertEqual(unit_price(50.0, 260), 45.0)

    def test_unit_price_bulk_264(self):
        self.assertEqual(unit_price(50.0, 264), 45.0)

    def test_unit_price_bulk_268(self):
        self.assertEqual(unit_price(50.0, 268), 45.0)

    def test_unit_price_bulk_272(self):
        self.assertEqual(unit_price(50.0, 272), 45.0)

    def test_unit_price_bulk_276(self):
        self.assertEqual(unit_price(50.0, 276), 45.0)

    def test_unit_price_bulk_280(self):
        self.assertEqual(unit_price(50.0, 280), 45.0)

    def test_unit_price_bulk_284(self):
        self.assertEqual(unit_price(50.0, 284), 45.0)

    def test_unit_price_bulk_288(self):
        self.assertEqual(unit_price(50.0, 288), 45.0)

    def test_unit_price_bulk_292(self):
        self.assertEqual(unit_price(50.0, 292), 45.0)

    def test_unit_price_bulk_296(self):
        self.assertEqual(unit_price(50.0, 296), 45.0)

    def test_unit_price_bulk_300(self):
        self.assertEqual(unit_price(50.0, 300), 45.0)

    def test_unit_price_bulk_304(self):
        self.assertEqual(unit_price(50.0, 304), 45.0)

    def test_unit_price_bulk_308(self):
        self.assertEqual(unit_price(50.0, 308), 45.0)

    def test_unit_price_bulk_312(self):
        self.assertEqual(unit_price(50.0, 312), 45.0)

    def test_unit_price_bulk_316(self):
        self.assertEqual(unit_price(50.0, 316), 45.0)

    def test_unit_price_bulk_320(self):
        self.assertEqual(unit_price(50.0, 320), 45.0)

    def test_unit_price_bulk_324(self):
        self.assertEqual(unit_price(50.0, 324), 45.0)

    def test_unit_price_bulk_328(self):
        self.assertEqual(unit_price(50.0, 328), 45.0)

    def test_unit_price_bulk_332(self):
        self.assertEqual(unit_price(50.0, 332), 45.0)

    def test_unit_price_bulk_336(self):
        self.assertEqual(unit_price(50.0, 336), 45.0)

    def test_unit_price_bulk_340(self):
        self.assertEqual(unit_price(50.0, 340), 45.0)

    def test_unit_price_bulk_344(self):
        self.assertEqual(unit_price(50.0, 344), 45.0)

    def test_unit_price_bulk_348(self):
        self.assertEqual(unit_price(50.0, 348), 45.0)

    def test_unit_price_bulk_352(self):
        self.assertEqual(unit_price(50.0, 352), 45.0)

    def test_unit_price_bulk_356(self):
        self.assertEqual(unit_price(50.0, 356), 45.0)

    def test_unit_price_bulk_360(self):
        self.assertEqual(unit_price(50.0, 360), 45.0)

    def test_unit_price_bulk_364(self):
        self.assertEqual(unit_price(50.0, 364), 45.0)

    def test_unit_price_bulk_368(self):
        self.assertEqual(unit_price(50.0, 368), 45.0)

    def test_unit_price_bulk_372(self):
        self.assertEqual(unit_price(50.0, 372), 45.0)

    def test_unit_price_bulk_376(self):
        self.assertEqual(unit_price(50.0, 376), 45.0)

    def test_unit_price_bulk_380(self):
        self.assertEqual(unit_price(50.0, 380), 45.0)

    def test_unit_price_bulk_384(self):
        self.assertEqual(unit_price(50.0, 384), 45.0)

    def test_unit_price_bulk_388(self):
        self.assertEqual(unit_price(50.0, 388), 45.0)

    def test_unit_price_bulk_392(self):
        self.assertEqual(unit_price(50.0, 392), 45.0)

    def test_unit_price_bulk_396(self):
        self.assertEqual(unit_price(50.0, 396), 45.0)

    def test_restock_0(self):
        self.assertEqual(restock(0, 5), 5)

    def test_restock_2(self):
        self.assertEqual(restock(2, 5), 7)

    def test_restock_4(self):
        self.assertEqual(restock(4, 5), 9)

    def test_restock_6(self):
        self.assertEqual(restock(6, 5), 11)

    def test_restock_8(self):
        self.assertEqual(restock(8, 5), 13)

    def test_restock_10(self):
        self.assertEqual(restock(10, 5), 15)

    def test_restock_12(self):
        self.assertEqual(restock(12, 5), 17)

    def test_restock_14(self):
        self.assertEqual(restock(14, 5), 19)

    def test_restock_16(self):
        self.assertEqual(restock(16, 5), 21)

    def test_restock_18(self):
        self.assertEqual(restock(18, 5), 23)

    def test_restock_20(self):
        self.assertEqual(restock(20, 5), 25)

    def test_restock_22(self):
        self.assertEqual(restock(22, 5), 27)

    def test_restock_24(self):
        self.assertEqual(restock(24, 5), 29)

    def test_restock_26(self):
        self.assertEqual(restock(26, 5), 31)

    def test_restock_28(self):
        self.assertEqual(restock(28, 5), 33)

    def test_restock_30(self):
        self.assertEqual(restock(30, 5), 35)

    def test_restock_32(self):
        self.assertEqual(restock(32, 5), 37)

    def test_restock_34(self):
        self.assertEqual(restock(34, 5), 39)

    def test_restock_36(self):
        self.assertEqual(restock(36, 5), 41)

    def test_restock_38(self):
        self.assertEqual(restock(38, 5), 43)

    def test_restock_40(self):
        self.assertEqual(restock(40, 5), 45)

    def test_restock_42(self):
        self.assertEqual(restock(42, 5), 47)

    def test_restock_44(self):
        self.assertEqual(restock(44, 5), 49)

    def test_restock_46(self):
        self.assertEqual(restock(46, 5), 51)

    def test_restock_48(self):
        self.assertEqual(restock(48, 5), 53)

    def test_restock_50(self):
        self.assertEqual(restock(50, 5), 55)

    def test_restock_52(self):
        self.assertEqual(restock(52, 5), 57)

    def test_restock_54(self):
        self.assertEqual(restock(54, 5), 59)

    def test_restock_56(self):
        self.assertEqual(restock(56, 5), 61)

    def test_restock_58(self):
        self.assertEqual(restock(58, 5), 63)

    def test_restock_60(self):
        self.assertEqual(restock(60, 5), 65)

    def test_restock_62(self):
        self.assertEqual(restock(62, 5), 67)

    def test_restock_64(self):
        self.assertEqual(restock(64, 5), 69)

    def test_restock_66(self):
        self.assertEqual(restock(66, 5), 71)

    def test_restock_68(self):
        self.assertEqual(restock(68, 5), 73)

    def test_restock_70(self):
        self.assertEqual(restock(70, 5), 75)

    def test_restock_72(self):
        self.assertEqual(restock(72, 5), 77)

    def test_restock_74(self):
        self.assertEqual(restock(74, 5), 79)

    def test_restock_76(self):
        self.assertEqual(restock(76, 5), 81)

    def test_restock_78(self):
        self.assertEqual(restock(78, 5), 83)

    def test_restock_80(self):
        self.assertEqual(restock(80, 5), 85)

    def test_restock_82(self):
        self.assertEqual(restock(82, 5), 87)

    def test_restock_84(self):
        self.assertEqual(restock(84, 5), 89)

    def test_restock_86(self):
        self.assertEqual(restock(86, 5), 91)

    def test_restock_88(self):
        self.assertEqual(restock(88, 5), 93)

    def test_restock_90(self):
        self.assertEqual(restock(90, 5), 95)

    def test_restock_92(self):
        self.assertEqual(restock(92, 5), 97)

    def test_restock_94(self):
        self.assertEqual(restock(94, 5), 99)

    def test_restock_96(self):
        self.assertEqual(restock(96, 5), 101)

    def test_restock_98(self):
        self.assertEqual(restock(98, 5), 103)

    def test_restock_100(self):
        self.assertEqual(restock(100, 5), 105)

    def test_restock_102(self):
        self.assertEqual(restock(102, 5), 107)

    def test_restock_104(self):
        self.assertEqual(restock(104, 5), 109)

    def test_restock_106(self):
        self.assertEqual(restock(106, 5), 111)

    def test_restock_108(self):
        self.assertEqual(restock(108, 5), 113)

    def test_restock_110(self):
        self.assertEqual(restock(110, 5), 115)

    def test_restock_112(self):
        self.assertEqual(restock(112, 5), 117)

    def test_restock_114(self):
        self.assertEqual(restock(114, 5), 119)

    def test_restock_116(self):
        self.assertEqual(restock(116, 5), 121)

    def test_restock_118(self):
        self.assertEqual(restock(118, 5), 123)

    def test_total_value_1(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 1}], {"a": 2.5}), 2.5)

    def test_total_value_2(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 2}], {"a": 2.5}), 5.0)

    def test_total_value_3(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 3}], {"a": 2.5}), 7.5)

    def test_total_value_4(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 4}], {"a": 2.5}), 10.0)

    def test_total_value_5(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 5}], {"a": 2.5}), 12.5)

    def test_total_value_6(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 6}], {"a": 2.5}), 15.0)

    def test_total_value_7(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 7}], {"a": 2.5}), 17.5)

    def test_total_value_8(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 8}], {"a": 2.5}), 20.0)

    def test_total_value_9(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 9}], {"a": 2.5}), 22.5)

    def test_total_value_10(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 10}], {"a": 2.5}), 25.0)

    def test_total_value_11(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 11}], {"a": 2.5}), 27.5)

    def test_total_value_12(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 12}], {"a": 2.5}), 30.0)

    def test_total_value_13(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 13}], {"a": 2.5}), 32.5)

    def test_total_value_14(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 14}], {"a": 2.5}), 35.0)

    def test_total_value_15(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 15}], {"a": 2.5}), 37.5)

    def test_total_value_16(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 16}], {"a": 2.5}), 40.0)

    def test_total_value_17(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 17}], {"a": 2.5}), 42.5)

    def test_total_value_18(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 18}], {"a": 2.5}), 45.0)

    def test_total_value_19(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 19}], {"a": 2.5}), 47.5)

    def test_total_value_20(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 20}], {"a": 2.5}), 50.0)

    def test_total_value_21(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 21}], {"a": 2.5}), 52.5)

    def test_total_value_22(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 22}], {"a": 2.5}), 55.0)

    def test_total_value_23(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 23}], {"a": 2.5}), 57.5)

    def test_total_value_24(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 24}], {"a": 2.5}), 60.0)

    def test_total_value_25(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 25}], {"a": 2.5}), 62.5)

    def test_total_value_26(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 26}], {"a": 2.5}), 65.0)

    def test_total_value_27(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 27}], {"a": 2.5}), 67.5)

    def test_total_value_28(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 28}], {"a": 2.5}), 70.0)

    def test_total_value_29(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 29}], {"a": 2.5}), 72.5)

    def test_total_value_30(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 30}], {"a": 2.5}), 75.0)

    def test_total_value_31(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 31}], {"a": 2.5}), 77.5)

    def test_total_value_32(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 32}], {"a": 2.5}), 80.0)

    def test_total_value_33(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 33}], {"a": 2.5}), 82.5)

    def test_total_value_34(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 34}], {"a": 2.5}), 85.0)

    def test_total_value_35(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 35}], {"a": 2.5}), 87.5)

    def test_total_value_36(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 36}], {"a": 2.5}), 90.0)

    def test_total_value_37(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 37}], {"a": 2.5}), 92.5)

    def test_total_value_38(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 38}], {"a": 2.5}), 95.0)

    def test_total_value_39(self):
        self.assertEqual(total_value([{"sku": "a", "name": "A", "qty": 39}], {"a": 2.5}), 97.5)

    def test_bulk_discount_rounding(self):
        self.assertEqual(unit_price(22.22, 10), 21.11)

    def test_restock_negative(self):
        with self.assertRaises(ValueError):
            restock(10, -3)

    def test_export_csv_header(self):
        rows = export_rows([{"sku": "X1", "name": "Bolt", "qty": 4}])
        self.assertEqual(rows[0]["sku"], "X1")


if __name__ == "__main__":
    unittest.main()
