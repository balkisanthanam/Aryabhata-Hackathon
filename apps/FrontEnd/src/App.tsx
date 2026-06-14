import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { useEffect } from 'react';
import { MainDashboard } from './pages/MainDashboard';
import { PracticeDashboard } from './pages/PracticeDashboard';
import { PracticeSession } from './pages/PracticeSession';
import { SolutionFeedback } from './pages/SolutionFeedback';
import { ChallengeDashboard } from './pages/ChallengeDashboard';
import { PerformanceCompass } from './pages/PerformanceCompass';
import { AccentSession } from './pages/AccentSession';
// import { UnderConstruction } from './components/common/UnderConstruction';
import { useUserStore } from './store/useUserStore';
import { loginUser } from './lib/api';

function App() {
    const setUser = useUserStore(state => state.setUser);

    useEffect(() => {
        const initSession = async () => {
            try {
                const userData = await loginUser();
                console.log('Session initialized:', userData);
                setUser(
                    userData.userId,
                    userData.userName,
                    userData.userClass,
                    userData.board,
                    userData.goal,
                    userData.email
                );
            } catch (error) {
                console.error('Failed to initialize session:', error);
            }
        };

        initSession();
    }, [setUser]);

    return (
        <Router>
            <Routes>
                <Route path="/" element={<MainDashboard />} />
                <Route path="/practice" element={<PracticeDashboard />} />
                <Route path="/practice/:chapterId" element={<PracticeSession />} />
                <Route path="/feedback" element={<SolutionFeedback />} />
                {/* Add other routes later */}
                <Route path="/accent/:chapterId" element={<AccentSession />} />
                <Route path="/challenge" element={<ChallengeDashboard />} />
                <Route path="/analytics" element={<PerformanceCompass />} />
                {/* <Route path="/challenge" element={<UnderConstruction title="Challenge" />} /> */}
            </Routes>
        </Router>
    )
}

export default App
