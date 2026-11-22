"""Run the pinned Sport wizard with Offroad's connection checks."""

from pathlib import Path
import sys


def main(engine, state, profile, actions):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ethernet import wired_route

    sys.path.insert(0, engine)
    from src import wizard

    if '--rollback' not in actions:
        selected = wizard.config.read(profile)
        expected = wizard.config.blank()['options']
        expected.update(oil_temperature_fix=True, coolant_temperature_fix=True)
        if ((selected['train'], selected['mu']) != wizard.config.SUPPORTED
                or selected['options'] != expected):
            raise ValueError('The Offroad temperature profile changed. Re-extract the original installer.')

    def checked_host(language, ask=input, previous=''):
        if '--rollback' not in actions:
            supported = wizard.pick((
                'Is this a Delphi 874B with software train MST2_EU_VW_P0635D and MU 0757?',
                'Üniteniz Delphi 874B, yazılım sürümü MST2_EU_VW_P0635D ve MU 0757 mi?',
            ), language)
            if not wizard.confirm(supported, language, ask):
                raise ValueError(wizard.pick(('Check the model and software versions before continuing.',
                                               'Devam etmeden önce model ve yazılım sürümünü kontrol edin.'), language))
        adapter = wizard.pick((
            'Does the adapter plugged into the head unit say D-Link DUB-E100 on its label?',
            'Multimedya ünitesine takılı adaptörün etiketinde D-Link DUB-E100 yazıyor mu?',
        ), language)
        if not wizard.confirm(adapter, language, ask):
            raise ValueError(wizard.pick(('Check the adapter label before continuing.',
                                           'Devam etmeden önce adaptörün etiketini kontrol edin.'), language))
        print(wizard.pick(('Use the suggested address only if it matches the address shown on the unit.',
                           'Önerilen adresi yalnızca ünitede görünen adresle aynıysa kullanın.'), language))
        host = request_host(language, ask, previous or '192.168.1.4')
        name, source = wired_route(host)
        print(wizard.pick(('Direct Ethernet connection', 'Doğrudan Ethernet bağlantısı'), language)
              + f' — {name} ({source})')
        return host

    request_host = wizard.request_host
    wizard.request_host = checked_host
    return wizard.main(['--state-dir', state, '--config', profile, *actions])


if __name__ == '__main__':
    engine, state, profile, *actions = sys.argv[1:]
    try:
        sys.exit(main(engine, state, profile, actions))
    except (OSError, ValueError) as error:
        print(f'Offroad installer stopped. {error}', file=sys.stderr)
        sys.exit(1)
