import { useQuery } from '@tanstack/react-query';
import { taggingApi } from '../services/api';

export function Categories() {
    const { data: categories, isLoading } = useQuery({
        queryKey: ['categories'],
        queryFn: () => taggingApi.getCategories().then(res => res.data),
    });

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-3xl font-bold">Categories & Tags</h1>
                <p className="text-[var(--text-muted)] mt-1">
                    Manage your expense categories and tags
                </p>
            </div>

            {isLoading ? (
                <div className="text-center text-[var(--text-muted)]">Loading...</div>
            ) : !categories || Object.keys(categories).length === 0 ? (
                <div className="text-center text-[var(--text-muted)]">
                    No categories found. Add your first category to get started.
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {Object.entries(categories as Record<string, string[]>).map(([category, tags]) => (
                        <div
                            key={category}
                            className="bg-[var(--surface)] rounded-xl border border-[var(--surface-light)] p-5"
                        >
                            <h3 className="font-semibold text-lg mb-3">{category}</h3>
                            <div className="flex flex-wrap gap-2">
                                {tags.map((tag) => (
                                    <span
                                        key={tag}
                                        className="px-3 py-1 rounded-full bg-[var(--surface-light)] text-sm text-[var(--text-muted)]"
                                    >
                                        {tag}
                                    </span>
                                ))}
                                {tags.length === 0 && (
                                    <span className="text-sm text-[var(--text-muted)]">No tags</span>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
