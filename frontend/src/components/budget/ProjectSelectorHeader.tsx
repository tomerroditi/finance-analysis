import React from "react";
import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";
import { SelectDropdown } from "../common/SelectDropdown";

interface ProjectSelectorHeaderProps {
  projects: string[];
  selectedProject: string;
  onSelect: (value: string) => void;
  onCreate: () => void;
  onDelete: () => void;
}

/** Project selector dropdown + New/Delete controls for the project view. */
export const ProjectSelectorHeader: React.FC<ProjectSelectorHeaderProps> = ({
  projects,
  selectedProject,
  onSelect,
  onCreate,
  onDelete,
}) => {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-3 md:gap-0 bg-[var(--surface)] p-4 rounded-2xl shadow-sm border border-[var(--surface-light)]">
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 md:gap-4 w-full md:w-auto">
        <label className="font-semibold text-sm md:text-base text-[var(--text-default)]">
          {t("budget.selectProject")}
        </label>
        <div className="w-full sm:w-64">
          <SelectDropdown
            options={
              projects.length > 0
                ? projects.map((p) => ({ label: p, value: p }))
                : []
            }
            value={selectedProject}
            onChange={onSelect}
            placeholder={
              projects.length === 0
                ? t("budget.noProjects")
                : t("budget.selectProject")
            }
            disabled={projects.length === 0}
            size="sm"
          />
        </div>
      </div>

      <div className="flex gap-2 w-full md:w-auto">
        <button
          onClick={onCreate}
          className="flex items-center gap-2 px-3 md:px-4 py-2 text-xs md:text-sm bg-[var(--primary)] text-white rounded-lg hover:bg-[var(--primary-dark)] transition-colors shadow-sm font-medium"
        >
          <Plus size={20} />
          {t("budget.newProject")}
        </button>
        {selectedProject && (
          <button
            onClick={onDelete}
            className="flex items-center gap-2 px-3 md:px-4 py-2 text-xs md:text-sm bg-red-500/10 border border-red-500/20 text-red-500 rounded-lg hover:bg-red-500/20 transition-colors shadow-sm font-medium"
          >
            <Trash2 size={20} />
            {t("common.delete")}
          </button>
        )}
      </div>
    </div>
  );
};
