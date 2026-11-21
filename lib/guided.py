"""Guided installation and recovery through the existing Offroad backend."""

import hashlib
from ipaddress import IPv4Address
import re

import native_menu as menu
from ethernet import wired_route
from receipt import Receipt, SCHEMA


TARGET = 'Delphi 874B / MST2_EU_VW_P0635D / 0757'
DEFAULT_HOST = IPv4Address('192.168.1.4')
PENDING = frozenset({'apply_pending', 'rollback_pending'})


class ChangeCancelled(Exception):
    """The user declined a guided change before the installer wrote to the unit."""


def read_enabled(session):
    _, scalars = menu.read_verified(session)
    return bool(scalars[menu.OWN_KEY] & 1)


def inspect(host, source=None):
    with menu.open_session(host, source) as session:
        return read_enabled(session)


def transact(action, host, identity_digest, directory, confirm_pending, confirm_write, source=None):
    """Capture the original bit before applying and restore it on explicit rollback."""
    store = Receipt(directory)
    with store.lock():
        receipt = store.load(host, identity_digest)
        phase = receipt['phase'] if receipt else None
        restoring = action == 'rollback'
        if restoring and receipt is None:
            raise ValueError('No recovery receipt exists in this folder')
        if phase in PENDING:
            if not restoring:
                raise ValueError('A previous write is uncertain. Restart, run --inspect, then use --rollback with this folder.')
            if not confirm_pending():
                raise ChangeCancelled

        with menu.open_session(host, source) as session:
            observed = read_enabled(session)
            new_receipt = not restoring and phase in (None, 'restored')
            if new_receipt:
                receipt = {
                    'schema': SCHEMA, 'host': str(host), 'identity_sha256': identity_digest,
                    'original_enabled': observed, 'phase': 'prepared',
                }
                phase = 'prepared'

            original = receipt['original_enabled']
            desired = original if restoring else True
            if ((phase in ('prepared', 'restored') and observed != original)
                    or (phase == 'applied' and not observed and (not restoring or original))):
                raise ValueError('Offroad changed outside the saved operation. Review the receipt before proceeding.')

            changed = observed != desired
            if changed:
                if not confirm_write(observed, original, desired):
                    raise ChangeCancelled
                if new_receipt:
                    store.save(receipt)

                def before_write(report):
                    if report['state'] == 'ONE_SCALAR_WRITE_ATTEMPTING':
                        receipt['phase'] = 'rollback_pending' if restoring else 'apply_pending'
                        store.save(receipt)

                menu.change(session, desired, before_write, expected_enabled=observed)

            final_phase = 'restored' if restoring else 'applied'
            if receipt['phase'] != final_phase:
                receipt['phase'] = final_phase
                store.save(receipt)
            return desired, changed


def run(action, host, directory, language):
    if language is None:
        selection = input('Language / Dil [EN/tr]: ').strip().casefold()
        language = {'': 'en', 'en': 'en', 'tr': 'tr'}.get(selection)
        if language is None:
            raise ValueError('Choose en or tr / en veya tr seçin')

    def localized(english, turkish):
        return turkish if language == 'tr' else english

    def setting(enabled):
        return localized('On', 'Açık') if enabled else localized('Off', 'Kapalı')

    def confirm(english, turkish):
        token = localized('YES', 'EVET')
        return input(f'{localized(english, turkish)} [{token}]: ').strip().upper() == token

    titles = {
        'apply': ('Show the Offroad / Compass page', 'Offroad / Pusula sayfasını göster'),
        'inspect': ('Check whether Offroad / Compass is on', 'Offroad / Pusula ayarını kontrol et'),
        'rollback': ('Restore your saved Offroad / Compass setting', 'Kaydedilen Offroad / Pusula ayarını geri yükle'),
    }
    print(localized(*titles[action]))
    print(localized('\n1. Connect and check your head unit', '\n1. Ünitenizi bağlayın ve bilgilerini kontrol edin'))
    print(localized(
        'Connect this computer to your own head unit using its existing wired maintenance connection.\n'
        'Check for D-Link DUB-E100 on the adapter plugged into the head unit. Connect its Ethernet cable to this computer.\n'
        'Have the IP address shown in the head unit’s service menu ready. See README.md for connection requirements.',
        'Bilgisayarı kendi ünitenize, ünitenin mevcut kablolu bakım bağlantısı üzerinden bağlayın.\n'
        'Üniteye takılan adaptörün üzerinde D-Link DUB-E100 yazdığını kontrol edin. Ağ kablosunu bu bilgisayara bağlayın.\n'
        'Ünitenin servis menüsünde görünen IP adresini hazır bulundurun. Bağlantı koşulları README.md dosyasındadır.',
    ))
    print(localized(
        f'For navigation-equipped units with these details: {TARGET}',
        f'Navigasyonlu ünitenizin bilgileri şöyle olmalıdır: {TARGET}',
    ))
    print(localized(
        'Press Enter at a confirmation to stop before changing any setting.',
        'Herhangi bir onay sorusunda Enter tuşuna basarak ayarı değiştirmeden çıkabilirsiniz.',
    ))
    if not confirm(
        'Is the D-Link adapter connected, and do the details above match your head unit?',
        'D-Link adaptörü takılı mı ve yukarıdaki bilgiler ünitenizle eşleşiyor mu?',
    ):
        raise ValueError(localized('Stopped before connecting.', 'Bağlantı kurulmadan iptal edildi.'))

    if host is None:
        print(localized('Press Enter only if the displayed default matches the IP address on your head unit.',
                        'Yalnızca varsayılan IP adresi ünitenizdeki adresle aynıysa Enter’a basın.'))
        address = input(localized(f'Head-unit IP address [Enter = {DEFAULT_HOST}]: ',
                                  f'Ünitenin IP adresi [Enter = {DEFAULT_HOST}]: ')).strip()
        try:
            host = IPv4Address(address) if address else DEFAULT_HOST
        except ValueError as error:
            raise ValueError(localized('Enter the IP address as four numbers separated by dots.',
                                       'IP adresini noktalarla ayrılmış dört sayı olarak girin.')) from error

    try:
        route = wired_route(host)
    except ValueError as error:
        raise ValueError(localized(
            'Windows could not verify a direct Ethernet connection to that IP. Check the cable and the IP address shown on the unit. Check the Ethernet setup in README.md, then run the wizard again.',
            'Windows bu IP adresine doğrudan Ethernet bağlantısını doğrulayamadı. Kabloyu ve ünitede görünen IP adresini kontrol edin. README.md dosyasındaki bağlantı adımlarını kontrol edip yeniden deneyin.',
        )) from error
    source = None
    if route is not None:
        name, source = route
        print(localized(f'Windows found an active Ethernet connection: {name} ({source}).',
                        f'Windows etkin bir Ethernet bağlantısı buldu: {name} ({source}).'))
    else:
        print(localized('Check the adapter and cable by sight. The installer will test the connection by reading the unit.',
                        'Adaptörü ve kabloyu gözle kontrol edin. Yükleyici üniteden bilgi okuyarak bağlantıyı deneyecek.'))

    if action != 'inspect':
        print(localized('\n2. Recovery details', '\n2. Geri yükleme bilgileri'))
        print(localized(
            'Keep this private code. You’ll enter it again if you restore the saved setting for this unit.',
            'Bu özel kodu saklayın. Ünitenin kaydedilen ayarını geri yüklerken aynı kodu gireceksiniz.',
        ))
        identity = input(localized(
            'Enter a code unique to this unit, such as its serial number: ',
            'Bu üniteye özgü bir kod girin (örneğin seri numarası): ',
        )).strip().upper()
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9._-]{0,63}', identity):
            raise ValueError(localized(
                'Start with a letter or number. Use up to 64 letters A–Z, numbers, dots, underscores or hyphens.',
                'Harf veya rakamla başlayın. En fazla 64 karakter kullanın: A–Z arası harfler, rakamlar, nokta, alt çizgi veya kısa çizgi.',
            ))
        identity_digest = hashlib.sha256(f'{TARGET}\n{identity}'.encode('ascii')).hexdigest()
        print(localized(f'Recovery folder: {directory}', f'Kurtarma klasörü: {directory}'))

    def confirm_pending():
        print(localized(
            'The installer could not verify the last change. Restart the unit normally and check its current setting with --inspect before trying to restore it.',
            'Son değişiklik doğrulanamadı. Geri yüklemeyi denemeden önce üniteyi normal şekilde yeniden başlatın ve --inspect ile mevcut ayarı kontrol edin.',
        ))
        return confirm('Have you restarted the unit and checked the setting?',
                       'Üniteyi yeniden başlatıp ayarı kontrol ettiniz mi?')

    def confirm_write(current, original, desired):
        print(localized(
            f'Checked the unit’s configuration. Offroad / Compass is currently {setting(current)}.',
            f'Ünite yapılandırması kontrol edildi. Offroad / Pusula ayarı şu anda {setting(current)}.',
        ))
        print(localized(
            f'This changes the Offroad / Compass visibility setting to {setting(desired)}.',
            f'Offroad / Pusula görünürlük ayarı {setting(desired)} olarak değişecek.',
        ))
        print(localized(
            f'Your original setting for rollback is {setting(original)}.',
            f'Geri yükleme için kullanılacak ilk ayar: {setting(original)}.',
        ))
        print(localized(
            'Keep the vehicle parked, the unit powered and the cable connected until verification finishes.',
            'Doğrulama tamamlanana kadar aracı park halinde, üniteyi açık ve kabloyu bağlı tutun.',
        ))
        approved = confirm('Are you ready to change this setting now?',
                           'Bu ayarı şimdi değiştirmeye hazır mısınız?')
        if approved:
            print(localized(
                'Rechecking the setting before making the change.',
                'Değişiklikten önce ayar yeniden kontrol ediliyor.',
            ))
        return approved

    title = localized('Check the current setting', 'Mevcut ayarı kontrol edin')
    print(f'\n{2 if action == "inspect" else 3}. {title}')
    print(localized(
        f'The installer will check the configuration and read the Offroad / Compass setting at {host}.',
        f'Yükleyici {host} adresindeki ünitenin yapılandırmasını ve Offroad / Pusula ayarını okuyacak.',
    ))
    try:
        if action == 'inspect':
            enabled, changed = inspect(host, source), False
        else:
            enabled, changed = transact(action, host, identity_digest, directory, confirm_pending, confirm_write, source)
    except ChangeCancelled:
        raise ValueError(localized(
            'Stopped. No unit settings changed during this run.',
            'İşlem durduruldu. Bu çalıştırmada ünitenin ayarları değişmedi.',
        )) from None
    except (OSError, ValueError) as error:
        message = localized(
            f'The installer could not finish. Details: {error}',
            f'Yükleyici işlemi tamamlayamadı. Teknik ayrıntı (İngilizce): {error}',
        )
        if isinstance(error, (ConnectionError, TimeoutError)):
            message += '\n' + localized(
                'Check the cable, confirm the IP address in the head unit’s service menu, and make sure the unit is powered.',
                'Kabloyu ve ünitenin servis menüsündeki IP adresini kontrol edin. Ünitenin açık olduğundan emin olun.',
            )
        if action != 'inspect':
            message += '\n' + localized(
                'If the installer stopped after you approved a change, keep the recovery folder, restart the unit normally and run --inspect before retrying recovery.',
                'İşlem değişikliği onayladıktan sonra durduysa kurtarma klasörünü saklayın. Yeniden geri yüklemeyi denemeden önce üniteyi normal şekilde yeniden başlatın ve --inspect komutunu çalıştırın.',
            )
        raise ValueError(message) from None

    print(localized(f'Verified Offroad / Compass setting: {setting(enabled)}.',
                    f'Doğrulanan Offroad / Pusula ayarı: {setting(enabled)}.'))
    if action != 'inspect':
        if not changed:
            print(localized('The setting already matches. No unit settings changed.',
                            'Ayar zaten istenen durumda. Ünitenin ayarları değişmedi.'))
        print(localized(
            f'Keep the recovery folder private. After a normal restart, check that the page is {"visible" if enabled else "hidden"} in the car’s menus.',
            f'Kurtarma klasörünü paylaşmayın. Üniteyi normal şekilde yeniden başlattıktan sonra sayfanın menüde {"göründüğünü" if enabled else "gizlendiğini"} kontrol edin.',
        ))
