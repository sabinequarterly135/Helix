import { useTranslation } from 'react-i18next'
import { WizardFlow } from '@/components/wizard/WizardFlow'

export default function WizardPage() {
  const { t } = useTranslation()

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">{t('wizard.title')}</h1>
        <p className="text-muted-foreground text-sm mt-1">
          {t('wizard.subtitle')}
        </p>
      </div>
      <WizardFlow />
    </div>
  )
}
