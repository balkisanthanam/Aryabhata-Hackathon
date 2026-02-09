import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface UserState {
    userId: number | null;
    userName: string | null;
    userClass: string | null;
    board: string | null;
    goal: string | null;
    email: string | null;

    // Actions
    setUser: (id: number, name: string, userClass?: string, board?: string, goal?: string, email?: string) => void;
    updateContext: (userClass: string, board: string) => void;
    clearUser: () => void;
}

export const useUserStore = create<UserState>()(
    persist(
        (set) => ({
            userId: null,
            userName: null,
            userClass: null,
            board: null,
            goal: null,
            email: null,

            setUser: (id, name, userClass, board, goal, email) =>
                set({
                    userId: id,
                    userName: name,
                    userClass: userClass || null,
                    board: board || null,
                    goal: goal || null,
                    email: email || null
                }),

            updateContext: (userClass, board) =>
                set({ userClass, board }),

            clearUser: () =>
                set({
                    userId: null,
                    userName: null,
                    userClass: null,
                    board: null
                }),
        }),
        {
            name: 'aryabhatta-user-storage', // name of the item in the storage (must be unique)
        }
    )
);
