import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { useAppStore } from '../../stores/appStore';

export function Layout() {
    const { sidebarOpen } = useAppStore();

    return (
        <div className="min-h-screen bg-[var(--background)]">
            <Sidebar />
            <main
                className={`transition-all duration-300 ${sidebarOpen ? 'ml-64' : 'ml-20'
                    }`}
            >
                <div className="p-8">
                    <Outlet />
                </div>
            </main>
        </div>
    );
}
