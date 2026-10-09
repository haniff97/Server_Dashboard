import unittest
from services.tnb_tariff import calculate_tnb_cost, allocate_tnb_cost

class TariffTests(unittest.TestCase):
    def bill(self, kwh, month='2026-10'):
        return calculate_tnb_cost(kwh, year_month=month)

    def test_incentive_boundaries(self):
        self.assertEqual(self.bill(200), 38.86)
        self.assertEqual(self.bill(250), 49.84)
        self.assertEqual(self.bill(300), 65.79)
        self.assertEqual(self.bill(400), 111.48)
        self.assertEqual(self.bill(600), 215.98)
        self.assertGreater(self.bill(200.01), self.bill(200))

    def test_protection_and_high_usage(self):
        self.assertEqual(self.bill(800), 328.62)
        self.assertGreater(self.bill(800.01), self.bill(800)+10)
        self.assertGreater(self.bill(1500.01), self.bill(1500)+100)
        self.assertGreater(self.bill(700, '2026-08'), self.bill(700))

    def test_allocation_adds_to_one_bill(self):
        shares = [allocate_tnb_cost(k, 900, year_month='2026-10') for k in (200,300,400)]
        self.assertAlmostEqual(sum(shares), self.bill(900), places=5)
        self.assertEqual(allocate_tnb_cost(0, 0), 0)

    def test_history_uses_each_month(self):
        from unittest.mock import patch
        from services import db
        points = [{'date_str': '2026-09-30', 'kwh': 2},
                  {'hour_str': '2026-10-01 12:00:00', 'kwh': 3},
                  {'date_str': '2026-10-02', 'kwh': 4}]
        with patch.object(db, 'estimate_usage_cost', side_effect=[1, 2]) as estimate:
            self.assertEqual(db.estimate_history_cost(points), 3)
            self.assertEqual(estimate.call_args_list[0].args, (2, '2026-09'))
            self.assertEqual(estimate.call_args_list[1].args, (7, '2026-10'))

    def test_unknown_future_rate_and_bad_usage(self):
        for value in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError): self.bill(value)
        with self.assertRaises(ValueError): self.bill(900, '2026-11')
        with self.assertRaises(ValueError): allocate_tnb_cost(10, 5)
        self.assertEqual(self.bill(200, '2026-11'), 38.86)

if __name__ == '__main__': unittest.main()
