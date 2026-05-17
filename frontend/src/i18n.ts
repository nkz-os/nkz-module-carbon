import { i18n } from '@nekazari/sdk';
import en from './locales/en/carbon.json';
import es from './locales/es/carbon.json';
import ca from './locales/ca/carbon.json';
import eu from './locales/eu/carbon.json';
import fr from './locales/fr/carbon.json';
import pt from './locales/pt/carbon.json';

const NS = 'carbon';

function register(): void {
  const add = i18n && 'addResourceBundle' in i18n ? i18n.addResourceBundle : undefined;
  if (typeof add !== 'function') return;
  for (const [lang, res] of Object.entries({ en, es, ca, eu, fr, pt })) {
    add.call(i18n, lang, NS, res, true, true);
  }
}

register();
