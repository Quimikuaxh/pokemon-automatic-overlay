import unittest

from pvo.geometry import (
    center_box,
    clamp_region,
    fit_aspect,
    scale_region,
    unscale_region,
)


class TestGeometry(unittest.TestCase):
    def test_fit_aspect_wider_box_limits_by_height(self):
        # caja 400x100, aspecto 1.5 → limita por alto: 150x100
        self.assertEqual(fit_aspect(400, 100, 1.5), (150, 100))

    def test_fit_aspect_taller_box_limits_by_width(self):
        # caja 100x400, aspecto 1.5 → limita por ancho: 100x66
        self.assertEqual(fit_aspect(100, 400, 1.5), (100, 67))

    def test_fit_aspect_exact(self):
        self.assertEqual(fit_aspect(240, 160, 1.5), (240, 160))

    def test_fit_aspect_degenerate(self):
        self.assertEqual(fit_aspect(0, 100, 1.5), (0, 0))

    def test_center_box(self):
        # inner 150x100 dentro de outer en (10,20,400,100) → centrado horizontal
        self.assertEqual(center_box((10, 20, 400, 100), (150, 100)), (135, 20, 150, 100))

    def test_scale_unscale_roundtrip(self):
        r = (12, 8, 32, 16)
        self.assertEqual(unscale_region(scale_region(r, 3), 3), r)

    def test_unscale_zero_raises(self):
        with self.assertRaises(ValueError):
            unscale_region((1, 2, 3, 4), 0)

    def test_clamp_region_inside(self):
        self.assertEqual(clamp_region((5, 5, 10, 10), 240, 160), (5, 5, 10, 10))

    def test_clamp_region_overflow(self):
        # se sale por la derecha/abajo → se recorta al borde
        self.assertEqual(clamp_region((230, 150, 50, 50), 240, 160), (230, 150, 10, 10))

    def test_clamp_region_negative(self):
        self.assertEqual(clamp_region((-10, -10, 20, 20), 240, 160), (0, 0, 10, 10))


if __name__ == "__main__":
    unittest.main()
