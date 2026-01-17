import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import { testingApi } from '../services/api';
import { useQueryClient } from '@tanstack/react-query';

interface TestModeContextType {
    isTestMode: boolean;
    toggleTestMode: (enabled: boolean) => Promise<void>;
    isLoading: boolean;
}

const TestModeContext = createContext<TestModeContextType | undefined>(undefined);

export function TestModeProvider({ children }: { children: ReactNode }) {
    const [isTestMode, setIsTestMode] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const queryClient = useQueryClient();

    useEffect(() => {
        // Fetch initial status
        testingApi.getTestModeStatus()
            .then(res => {
                setIsTestMode(res.data.test_mode);
            })
            .catch(err => {
                console.error("Failed to fetch test mode status:", err);
            })
            .finally(() => {
                setIsLoading(false);
            });
    }, []);

    const toggleTestMode = async (enabled: boolean) => {
        try {
            const res = await testingApi.toggleTestMode(enabled);
            setIsTestMode(res.data.test_mode);
            // Invalidate all queries to force refetch with new DB/Credentials
            queryClient.invalidateQueries();
        } catch (err) {
            console.error("Failed to toggle test mode:", err);
            throw err;
        }
    };

    return (
        <TestModeContext.Provider value={{ isTestMode, toggleTestMode, isLoading }}>
            {children}
        </TestModeContext.Provider>
    );
}

export function useTestMode() {
    const context = useContext(TestModeContext);
    if (context === undefined) {
        throw new Error('useTestMode must be used within a TestModeProvider');
    }
    return context;
}
