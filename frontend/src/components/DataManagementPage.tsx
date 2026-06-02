import { useMemo, useState } from "react";

import CsvDataPanel from "./CsvDataPanel";

import DictionaryPanel from "./DictionaryPanel";



export type DataManagementTab = "csv" | "dictionary";



interface DataManagementPageProps {

  onClose: () => void;

  onPoolChange?: () => void;

  analysisBusy?: boolean;

}



export default function DataManagementPage({

  onClose,

  onPoolChange,

  analysisBusy = false,

}: DataManagementPageProps) {

  const [tab, setTab] = useState<DataManagementTab>("csv");



  const tabs = useMemo(

    () =>

      [

        { id: "csv" as const, label: "CSV 数据池" },

        { id: "dictionary" as const, label: "埋点字典" },

      ] satisfies { id: DataManagementTab; label: string }[],

    []

  );



  return (

    <div className="min-h-screen">

      <header className="dash-top">

        <div className="flex w-full flex-wrap items-center justify-between gap-3">

          <div>

            <h1 className="dash-title">数据管理</h1>

            <p className="dash-meta">管理 CSV 数据池与埋点字典口径，支持边测边改</p>

          </div>

          <button

            type="button"

            onClick={onClose}

            className="rounded-lg border border-slate-200/80 bg-white/80 px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-white"

          >

            返回看板

          </button>

        </div>

      </header>



      <div className="relative z-[1] mx-auto max-w-6xl px-6 pb-16 pt-5">

        <div className="mb-4 flex gap-2 border-b border-slate-200/80">

          {tabs.map((item) => (

            <button

              key={item.id}

              type="button"

              onClick={() => setTab(item.id)}

              className={`border-b-2 px-4 py-2 text-sm font-medium transition ${

                tab === item.id

                  ? "border-violet-500 text-violet-700"

                  : "border-transparent text-slate-500 hover:text-slate-800"

              }`}

            >

              {item.label}

            </button>

          ))}

        </div>



        {tab === "csv" && (

          <CsvDataPanel disabled={analysisBusy} onPoolChange={onPoolChange} />

        )}

        {tab === "dictionary" && <DictionaryPanel disabled={analysisBusy} />}

      </div>

    </div>

  );

}

