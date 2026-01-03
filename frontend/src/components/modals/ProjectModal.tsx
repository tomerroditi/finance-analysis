import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { budgetApi } from '../../services/api';

interface ProjectModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSubmit: (data: { category: string; total_budget: number }) => void;
    initialData?: { category: string; total_budget: number } | null;
    isEdit?: boolean;
}

export const ProjectModal: React.FC<ProjectModalProps> = ({
    isOpen,
    onClose,
    onSubmit,
    initialData,
    isEdit = false,
}) => {
    const [category, setCategory] = useState('');
    const [totalBudget, setTotalBudget] = useState<number>(0);

    const { data: availableCategories = [] } = useQuery({
        queryKey: ['availableProjects'],
        queryFn: () => budgetApi.getAvailableProjects().then(res => res.data),
        enabled: isOpen && !isEdit,
    });

    useEffect(() => {
        if (isOpen && initialData) {
            setCategory(initialData.category);
            setTotalBudget(initialData.total_budget);
        } else if (isOpen) {
            setCategory('');
            setTotalBudget(0);
        }
    }, [isOpen, initialData]);

    // Auto-select first available category when list loads and not in edit mode
    useEffect(() => {
        if (!isEdit && !category && availableCategories.length > 0) {
            setCategory(availableCategories[0]);
        }
    }, [availableCategories, category, isEdit]);

    if (!isOpen) return null;

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!category) return;
        onSubmit({ category, total_budget: Number(totalBudget) });
        onClose();
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
            <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl w-full max-w-md shadow-2xl animate-in zoom-in-95 duration-200">
                <div className="flex justify-between items-center p-6 border-b border-[var(--surface-light)]">
                    <h2 className="text-xl font-bold">{isEdit ? `Edit Project: ${category} - Total` : 'New Project'}</h2>
                    <button onClick={onClose} className="p-2 hover:bg-[var(--surface-light)] rounded-full transition-colors text-[var(--text-muted)]">
                        <X size={20} />
                    </button>
                </div>
                <form onSubmit={handleSubmit} className="p-6 space-y-4">
                    <div>
                        <label className="block text-xs font-bold uppercase text-[var(--text-muted)] mb-1.5">Project Name (Category)</label>
                        {isEdit ? (
                            <input
                                type="text"
                                value={category}
                                className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium disabled:opacity-50"
                                required
                                disabled
                            />
                        ) : (
                            <select
                                value={category}
                                onChange={(e) => setCategory(e.target.value)}
                                className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                                required
                            >
                                <option value="" disabled>Select a category</option>
                                {availableCategories.map((cat: string) => (
                                    <option key={cat} value={cat}>{cat}</option>
                                ))}
                                {availableCategories.length === 0 && (
                                    <option disabled>No categories available</option>
                                )}
                            </select>
                        )}
                        {!isEdit && availableCategories.length === 0 && (
                            <p className="mt-1 text-xs text-amber-500">
                                All categories already have projects or none are defined.
                            </p>
                        )}
                    </div>
                    <div>
                        <label className="block text-xs font-bold uppercase text-[var(--text-muted)] mb-1.5">Total Budget</label>
                        <input
                            type="number"
                            step="0.01"
                            value={totalBudget}
                            onChange={(e) => setTotalBudget(Number(e.target.value))}
                            className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                            required
                        />
                    </div>
                    <div className="pt-4 flex gap-3">
                        <button
                            type="button"
                            onClick={onClose}
                            className="flex-1 py-3 font-bold text-[var(--text-muted)] hover:text-[var(--text-default)] transition-colors"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            className="flex-1 py-3 bg-[var(--primary)] text-white font-bold rounded-xl hover:bg-[var(--primary-dark)] transition-all shadow-lg shadow-[var(--primary)]/20"
                        >
                            {isEdit ? 'Update' : 'Create'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};
