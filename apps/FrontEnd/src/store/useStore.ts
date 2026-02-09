import { create } from 'zustand';

interface UserState {
    name: string;
    details: string; // e.g., "11, CBSE"
    goal: string; // e.g., "JEE"
    email: string;
}

interface AppState {
    user: UserState;
    streak: number;
    setUser: (user: UserState) => void;
}

export const useStore = create<AppState>((set) => ({
    user: {
        name: 'Visu',
        details: '11, CBSE',
        goal: 'JEE',
        email: 'xyz@abc.com'
    },
    streak: 12,
    setUser: (user) => set({ user }),
}));
