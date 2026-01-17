import { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { GlobalSearch } from './GlobalSearch';
import { useAppStore } from '../../stores/appStore';

import { Header } from './Header';

export function Layout() {
    const { sidebarOpen, searchOpen, setSearchOpen } = useAppStore();

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
                e.preventDefault();
                setSearchOpen(true);
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [setSearchOpen]);

    return (
        <div className="min-h-screen bg-[var(--background)]">
            <Sidebar />
            <GlobalSearch isOpen={searchOpen} onClose={() => setSearchOpen(false)} />
            <main
                className={`transition-all duration-300 ${sidebarOpen ? 'ml-64' : 'ml-20'
                    }`}
            >
                <Header />
                <div className="p-8">
                    <Outlet />
                </div>
            </main>
        </div>
    );
}
