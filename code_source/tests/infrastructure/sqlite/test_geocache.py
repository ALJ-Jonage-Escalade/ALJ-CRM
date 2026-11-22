"""Geocoding cache (geocache table): saved coordinates are read back, re-saving an address updates it."""

from support.member_db import MemberDbTestCase

from infrastructure.sqlite.geocache import GeocacheRepository

ADDRESS = "1 rue de la Paix, 69330, JONAGE, France"


class GeocacheRepositoryTest(MemberDbTestCase):

    def test_get_geocache_on_empty_table_is_empty(self):
        self.assertEqual(GeocacheRepository.get_geocache(), {})

    def test_saved_coordinates_are_read_back_by_address(self):
        GeocacheRepository.save_geocode(ADDRESS, 45.79, 5.04)
        self.assertEqual(GeocacheRepository.get_geocache(), {ADDRESS: [45.79, 5.04]})

    def test_saving_an_address_again_replaces_its_coordinates(self):
        GeocacheRepository.save_geocode(ADDRESS, None, None)
        GeocacheRepository.save_geocode(ADDRESS, 45.79, 5.04)
        self.assertEqual(GeocacheRepository.get_geocache(), {ADDRESS: [45.79, 5.04]})

    def test_unknown_address_is_cached_with_empty_coordinates(self):
        GeocacheRepository.save_geocode(ADDRESS, None, None)
        self.assertEqual(GeocacheRepository.get_geocache(), {ADDRESS: [None, None]})
