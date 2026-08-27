import type { RefObject } from 'react'
import Link from 'next/link'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import ModelPicker from './ModelPicker'
import SmartModePopover, { type SmartStrategy } from './SmartModePopover'
import { type ModelCatalogItem } from '@/types/catalog'
import { chatModelBarStrings } from './ChatModelBar.strings'

type ChatModelBarProps = {
  isMobile: boolean
  setMobileDrawerOpen: (v: boolean) => void
  sidebarOpen: boolean
  setSidebarOpen: (updater: (prev: boolean) => boolean) => void
  catalogError: boolean
  models: ModelCatalogItem[]
  model: ModelCatalogItem | null
  setModel: (m: ModelCatalogItem) => void
  loading: boolean
  token: string | null
  smartMode: boolean
  setSmartMode: (updater: (prev: boolean) => boolean) => void
  smartStrategy: SmartStrategy
  setSmartStrategy: (v: SmartStrategy) => void
  /** `mode` from the backend's smart_info event — the strategy that ran. */
  smartRunMode: string | null
  smartModel: string | null
  activeConversationId: string | null
  exportMenuOpen: boolean
  setExportMenuOpen: (updater: (prev: boolean) => boolean) => void
  exportMenuRef: RefObject<HTMLDivElement>
  exportConversation: (format: 'json' | 'markdown' | 'text') => void
  streaming: boolean
  cancel: () => void
}

export default function ChatModelBar({
  isMobile, setMobileDrawerOpen, sidebarOpen, setSidebarOpen,
  catalogError, models, model, setModel, loading, token,
  smartMode, setSmartMode, smartStrategy, setSmartStrategy, smartRunMode, smartModel,
  activeConversationId, exportMenuOpen, setExportMenuOpen, exportMenuRef, exportConversation,
  streaming, cancel,
}: ChatModelBarProps) {
  const lang = useLang()
  const s = chatModelBarStrings(lang)
  return (
    <div className="chat-model-bar">
      <div className="flex items-center gap-2">
        {/* Sidebar toggle (desktop) / hamburger (mobile) */}
        {isMobile ? (
          <button onClick={() => setMobileDrawerOpen(true)} className="conv-toggle-btn" title={s.conversations}>
            <Icon name="menu" size={18} />
          </button>
        ) : (
          <button onClick={() => setSidebarOpen(prev => !prev)} className="conv-toggle-btn" title={sidebarOpen ? s.closeSidebar : s.openSidebar}>
            <Icon name={sidebarOpen ? 'close' : 'menu'} size={16} />
          </button>
        )}

        <Icon name="models" size={18} className="text-[var(--accent)]" />
        {catalogError ? (
          <span className="text-sm text-[var(--danger)] flex items-center gap-1">
            <Icon name="close" size={14} /> {s.modelsLoadError}
          </span>
        ) : (
          <ModelPicker
            models={models}
            selected={model}
            onSelect={setModel}
            loading={loading}
            smartModeActive={smartMode}
          />
        )}
      </div>
      <div className="flex items-center gap-2">
        {/* Smart Mode. Was an on/off switch with a hardcoded English label;
            it now picks HOW smart mode chooses (auto / router / a combo) and
            reports which strategy the backend actually ran. */}
        <SmartModePopover
          token={token}
          smartMode={smartMode}
          setSmartMode={setSmartMode}
          strategy={smartStrategy}
          setStrategy={setSmartStrategy}
          ranMode={smartRunMode}
        />
        {smartMode && smartModel && (
          <span className="badge badge-accent text-[9px]" dir="ltr" title={s.smartModePicked}>
            🧠 {smartModel}
          </span>
        )}

        {/* Compare button */}
        <Link
          href="/compare"
          className="conv-toggle-btn no-underline"
          title={s.compareModels}
        >
          <Icon name="compare" size={16} />
        </Link>

        {/* Export dropdown */}
        {activeConversationId && (
          <div className="relative" ref={exportMenuRef}>
            <button
              onClick={() => setExportMenuOpen(prev => !prev)}
              className="conv-toggle-btn"
              title={s.export}
            >
              <Icon name="external" size={16} />
            </button>
            {exportMenuOpen && (
              <div className="export-dropdown">
                <button className="export-dropdown-item" onClick={() => exportConversation('json')}>
                  <Icon name="code" size={14} /> JSON
                </button>
                <button className="export-dropdown-item" onClick={() => exportConversation('markdown')}>
                  <Icon name="chat" size={14} /> Markdown
                </button>
                <button className="export-dropdown-item" onClick={() => exportConversation('text')}>
                  <Icon name="info" size={14} /> Text
                </button>
              </div>
            )}
          </div>
        )}

        {streaming && (
          <button onClick={cancel} className="btn btn-ghost btn-sm text-[var(--danger)]">
            <Icon name="close" size={14} />
            {s.stop}
          </button>
        )}
      </div>
    </div>
  )
}
