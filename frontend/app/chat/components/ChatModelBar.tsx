import type { RefObject } from 'react'
import Link from 'next/link'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import ModelPicker from './ModelPicker'
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
  smartMode: boolean
  setSmartMode: (updater: (prev: boolean) => boolean) => void
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
  catalogError, models, model, setModel, loading, smartMode, setSmartMode, smartModel,
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
        {/* Smart Mode toggle. Was a <label> wrapping an .sr-only
            checkbox — a 1×1px hit target in the tab order. role="switch"
            announces the state without needing the hidden input. */}
        <button
          type="button"
          role="switch"
          aria-checked={smartMode}
          onClick={() => setSmartMode(prev => !prev)}
          className="smart-mode-toggle"
          title={smartMode ? s.smartModeActive : s.smartModeInactive}
        >
          <span className={`smart-mode-switch ${smartMode ? 'smart-mode-on' : ''}`}>
            <span className="smart-mode-knob" />
          </span>
          <span className="select-none">Smart Mode</span>
        </button>
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
