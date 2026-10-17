from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from utils.validators import migrate_legacy_gambia_phone, normalize_gambia_phone, validate_gambia_phone


class NormalizeGambiaPhoneTest(SimpleTestCase):
    def test_strips_non_digits(self):
        self.assertEqual(normalize_gambia_phone('+220 877-000-000'), '877000000')

    def test_strips_a_leading_country_code(self):
        self.assertEqual(normalize_gambia_phone('220877000000'), '877000000')

    def test_leaves_a_bare_local_number_alone(self):
        self.assertEqual(normalize_gambia_phone('877000000'), '877000000')

    def test_blank_in_blank_out(self):
        self.assertEqual(normalize_gambia_phone(''), '')
        self.assertEqual(normalize_gambia_phone(None), '')


class ValidateGambiaPhoneTest(SimpleTestCase):
    def test_accepts_a_valid_nine_digit_number_and_normalizes_to_e164(self):
        self.assertEqual(validate_gambia_phone('877000000'), '+220877000000')
        self.assertEqual(validate_gambia_phone('+220 87 700 0000'), '+220877000000')

    def test_blank_passes_through_unchanged(self):
        self.assertEqual(validate_gambia_phone(''), '')

    def test_rejects_the_old_seven_digit_format(self):
        with self.assertRaises(ValidationError):
            validate_gambia_phone('7700000')

    def test_rejects_nine_digits_not_starting_with_8(self):
        with self.assertRaises(ValidationError):
            validate_gambia_phone('977000000')

    def test_rejects_wrong_lengths(self):
        with self.assertRaises(ValidationError):
            validate_gambia_phone('87700000')  # 8 digits
        with self.assertRaises(ValidationError):
            validate_gambia_phone('8770000000')  # 10 digits


class MigrateLegacyGambiaPhoneTest(SimpleTestCase):
    def test_7_2_4_prefixed_numbers_get_the_87_prefix(self):
        for first_digit in ('7', '2', '4'):
            local = first_digit + '123456'
            self.assertEqual(migrate_legacy_gambia_phone(local), f'+22087{local}')

    def test_3_5_prefixed_numbers_get_the_83_prefix(self):
        for first_digit in ('3', '5'):
            local = first_digit + '123456'
            self.assertEqual(migrate_legacy_gambia_phone(local), f'+22083{local}')

    def test_6_prefixed_numbers_get_the_86_prefix(self):
        local = '6123456'
        self.assertEqual(migrate_legacy_gambia_phone(local), f'+22086{local}')

    def test_the_last_seven_digits_of_the_result_are_always_the_original_number(self):
        # services/modempay_service.py's _local_phone() recovers an
        # account number by taking the last 7 digits of whatever it's
        # given -- the conversion must stay compatible with that.
        local = '7555555'
        converted = migrate_legacy_gambia_phone(local)
        self.assertTrue(converted.endswith(local))

    def test_already_new_format_numbers_are_left_alone(self):
        self.assertIsNone(migrate_legacy_gambia_phone('+220877000000'))

    def test_unmapped_leading_digit_is_left_alone(self):
        self.assertIsNone(migrate_legacy_gambia_phone('9123456'))

    def test_blank_is_left_alone(self):
        self.assertIsNone(migrate_legacy_gambia_phone(''))
