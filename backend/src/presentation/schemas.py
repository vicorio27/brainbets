from datetime import date
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class TennisMatch(BaseModel):
    matchId: str
    eventId: Optional[str] = None
    player1: str
    player2: str
    tournament: str
    eventDate: str
    eventTime: Optional[str] = None
    status: Optional[str] = None
    rankingPlayer1: Optional[int] = None
    rankingPlayer2: Optional[int] = None
    surface: Optional[str] = None
    formPlayer1: Optional[str] = None
    formPlayer2: Optional[str] = None
    h2h: Optional[str] = None
    acesAvgPlayer1: Optional[float] = None
    acesAvgPlayer2: Optional[float] = None
    eloPlayer1: Optional[float] = None
    eloPlayer2: Optional[float] = None
    eloSurfacePlayer1: Optional[float] = None
    eloSurfacePlayer2: Optional[float] = None
    oddsPlayer1: Optional[float] = None
    oddsPlayer2: Optional[float] = None
    tournamentTier: Optional[int] = None
    groundType: Optional[str] = None
    countryPlayer1: Optional[str] = None
    countryPlayer2: Optional[str] = None
    features: Optional[Dict[str, Any]] = None

class FootballMatch(BaseModel):
    matchId: str
    eventId: Optional[str] = None
    homeTeam: str
    awayTeam: str
    league: str
    eventDate: str
    eventTime: Optional[str] = None
    status: Optional[str] = None
    homePosition: Optional[int] = None
    awayPosition: Optional[int] = None
    homeForm: Optional[str] = None
    awayForm: Optional[str] = None
    homeXg: Optional[float] = None
    awayXg: Optional[float] = None
    homeXgAgainst: Optional[float] = None
    awayXgAgainst: Optional[float] = None
    homeCorners: Optional[float] = None
    awayCorners: Optional[float] = None
    headToHead: Optional[Dict[str, Any]] = None
    homeFormStats: Optional[Dict[str, Any]] = None
    awayFormStats: Optional[Dict[str, Any]] = None
    leagueStandings: Optional[List[Dict[str, Any]]] = None
    statsDataQuality: Optional[str] = None
    homeElo: Optional[float] = None
    awayElo: Optional[float] = None
    homeAttack: Optional[float] = None
    homeDefense: Optional[float] = None
    awayAttack: Optional[float] = None
    awayDefense: Optional[float] = None
    expectedHomeGoals: Optional[float] = None
    expectedAwayGoals: Optional[float] = None
    homeOdds: Optional[float] = None
    drawOdds: Optional[float] = None
    awayOdds: Optional[float] = None
    expertConsensus: Optional[Dict[str, Any]] = None
    features: Optional[Dict[str, Any]] = None

class MatchesResponse(BaseModel):
    generatedAt: str
    tennis: List[TennisMatch] = []
    football: List[FootballMatch] = []
    total: Optional[int] = None
    skip: Optional[int] = None
    limit: Optional[int] = None

class Prediction(BaseModel):
    predictionId: str
    matchId: str
    sport: str
    market: str
    prediction: str
    confidence: int = Field(ge=0, le=100)
    reasoning: str
    naturalLanguageReasoning: Optional[str] = None
    status: str
    probabilities: Optional[Dict[str, float]] = None
    modelContributions: Optional[Dict[str, float]] = None
    reasoningData: Optional[Dict[str, Any]] = None
    eventDate: Optional[str] = None
    createdAt: Optional[str] = None
    homeName: Optional[str] = None
    awayName: Optional[str] = None
    expectedValue: Optional[float] = None
    kellyFraction: Optional[float] = None
    calibratedConfidence: Optional[int] = None
    calibratedExpectedValue: Optional[float] = None

class PredictionsResponse(BaseModel):
    generatedAt: str
    predictions: List[Prediction] = []
    total: Optional[int] = None
    skip: Optional[int] = None
    limit: Optional[int] = None

class ResultItem(BaseModel):
    predictionId: str
    success: Optional[bool] = None
    actualResult: Optional[str] = "Pending"
    validationReason: str
    matchScore: Optional[str] = None

class ResultsResponse(BaseModel):
    generatedAt: str
    results: List[ResultItem] = []

class PredictionWithResult(BaseModel):
    prediction: Prediction
    result: Optional[ResultItem] = None

class AccuracyMetrics(BaseModel):
    totalPredictions: int
    successful: int
    failed: int
    accuracy: float
    accuracyTennis: float
    accuracyFootball: float

class DashboardSummary(BaseModel):
    lastMatchesUpdate: Optional[str] = None
    lastPredictionsUpdate: Optional[str] = None
    lastResultsUpdate: Optional[str] = None
    todayMatches: int = 0
    todayPredictions: int = 0
    todayAccuracy: Optional[float] = None
    latestMatches: int = 0
    latestPredictions: int = 0
    latestPredictedMatches: int = 0
    latestAccuracy: Optional[float] = None

class ScoreUpdateItem(BaseModel):
    matchId: str
    homeScore: int
    awayScore: int
    status: Optional[str] = "FINISHED"
    period: Optional[str] = "FULL_TIME"
    extraData: Optional[Dict[str, Any]] = None

class ScoresBulkPayload(BaseModel):
    generatedAt: Optional[str] = None
    scores: List[ScoreUpdateItem]

class PredictionSnapshot(BaseModel):
    matchId: str
    minute: int = 0
    periodLabel: Optional[str] = None
    homeScore: int = 0
    awayScore: int = 0
    # Tennis-specific
    homeSets: Optional[int] = None
    awaySets: Optional[int] = None
    homeGamesCurrent: Optional[int] = None
    awayGamesCurrent: Optional[int] = None
    homePoint: Optional[str] = None
    awayPoint: Optional[str] = None
    bestOf: Optional[int] = 3
    notes: Optional[str] = None

class SnapshotsPayload(BaseModel):
    generatedAt: Optional[str] = None
    snapshots: List[PredictionSnapshot]

class ProgressSummary(BaseModel):
    snapshots_received: int
    matches_found: int
    predictions_updated: int
    overall_avg_fulfillment: float
    bySport: Dict[str, Any]
    errors: List[str]
    generatedAt: str

class PredictionProgressSnapshot(BaseModel):
    snapshotAt: str
    minute: int
    periodLabel: Optional[str]
    homeScore: int
    awayScore: int
    fulfillmentPercent: float
    notes: Optional[str]

class PredictionProgressResponse(BaseModel):
    predictionId: str
    matchId: Optional[str]
    sport: Optional[str]
    market: str
    predictedOutcome: str
    snapshots: List[PredictionProgressSnapshot]


class ApiCacheStoreRequest(BaseModel):
    url: str
    method: Optional[str] = "GET"
    responseJson: Dict[str, Any]
    statusCode: Optional[int] = 200
    ttlSeconds: Optional[int] = 60


class ApiCacheEntry(BaseModel):
    url: str
    method: str
    responseJson: Dict[str, Any]
    statusCode: int
    cachedAt: str
    expiresAt: str
    hitCount: int


class ApiCacheLookupResponse(BaseModel):
    cached: bool
    entry: Optional[ApiCacheEntry] = None
