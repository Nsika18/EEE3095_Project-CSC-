/**
 ******************************************************************************
 * @file           : game.c
 * @brief          : Server-authoritative Tic-Tac-Toe engine (pure logic)
 ******************************************************************************
 */

#include "game.h"
#include "hardware.h"
#include <string.h>

/* --------------------------------------------------------------------------
 * Game engine — private state
 * -------------------------------------------------------------------------- */
static GameState   s_state;
static GamePlayer  s_turn;
static GameOutcome s_outcome;
static uint8_t     s_board[GAME_BOARD_CELLS];
static uint8_t     s_connected;

/* --------------------------------------------------------------------------
 * Private function prototypes
 * -------------------------------------------------------------------------- */
static void       reset_board(void);
static GamePlayer opponent(GamePlayer p);
static GamePlayer find_winner(const uint8_t *board);
static uint8_t    board_full(const uint8_t *board);

/* ==========================================================================
 * Game engine — lifecycle
 * ========================================================================== */
void Game_Init(void)
{
    s_connected = 0U;
    s_state     = GAME_STATE_IDLE;
    s_turn      = GAME_PLAYER_X;
    s_outcome   = GAME_OUTCOME_NONE;
    reset_board();
}

/* ==========================================================================
 * Game engine — commands
 * All state mutation happens AFTER full validation.
 * ========================================================================== */
GameStatus Game_Connect(void)
{
    /* If already connected, return BADCMD */
    if (s_connected) return GAME_ERR_BADCMD;

    s_connected = 1U;
    s_state     = GAME_STATE_IDLE;
    led_conn_set(1U);
    return GAME_OK;
}

GameStatus Game_Disconnect(void)
{
    if (!s_connected) return GAME_ERR_BADCMD;   /* not connected */

    s_connected = 0U;
    s_state     = GAME_STATE_IDLE;
    s_turn      = GAME_PLAYER_X;
    s_outcome   = GAME_OUTCOME_NONE;
    reset_board();
    led_conn_set(0U);
    return GAME_OK;
}

GameStatus Game_New(void)
{
    if (!s_connected)                      return GAME_ERR_BADCMD;
    if (s_state == GAME_STATE_IN_PROGRESS) return GAME_ERR_BADCMD;

    reset_board();
    s_turn    = GAME_PLAYER_X;
    s_outcome = GAME_OUTCOME_NONE;
    s_state   = GAME_STATE_IN_PROGRESS;
    return GAME_OK;
}

GameStatus Game_Move(uint8_t idx)
{
    if (!s_connected)                      return GAME_ERR_BADCMD;
    if (s_state != GAME_STATE_IN_PROGRESS) return GAME_ERR_NOGAME;
    if (idx >= GAME_BOARD_CELLS)           return GAME_ERR_RANGE;
    if (s_board[idx] != GAME_PLAYER_NONE)  return GAME_ERR_OCCUPIED;

    s_board[idx] = (uint8_t)s_turn;

    GamePlayer w = find_winner(s_board);
    if (w != GAME_PLAYER_NONE) {
        s_outcome = (w == GAME_PLAYER_X) ? GAME_OUTCOME_X : GAME_OUTCOME_O;
        s_state   = GAME_STATE_GAME_OVER;
        s_turn    = GAME_PLAYER_NONE;
        return GAME_OK;
    }
    if (board_full(s_board)) {
        s_outcome = GAME_OUTCOME_DRAW;
        s_state   = GAME_STATE_GAME_OVER;
        s_turn    = GAME_PLAYER_NONE;
        return GAME_OK;
    }

    s_turn = opponent(s_turn);
    return GAME_OK;
}

GameStatus Game_Resign(void)
{
    if (!s_connected || s_state != GAME_STATE_IN_PROGRESS) {
        return GAME_ERR_NOGAME;
    }

    GamePlayer w = opponent(s_turn);
    s_outcome = (w == GAME_PLAYER_X) ? GAME_OUTCOME_X : GAME_OUTCOME_O;
    s_state   = GAME_STATE_GAME_OVER;
    s_turn    = GAME_PLAYER_NONE;
    return GAME_OK;
}

GameStatus Game_State(void)
{
    return s_connected ? GAME_OK : GAME_ERR_BADCMD;
}

/* ==========================================================================
 * Game engine — queries
 * ========================================================================== */
GameState   Game_GetState(void)    { return s_state; }
GamePlayer  Game_GetTurn(void)     { return s_turn; }
GameOutcome Game_GetOutcome(void)  { return s_outcome; }
uint8_t     Game_IsConnected(void) { return s_connected; }

void Game_EncodeBoard(char out[GAME_BOARD_CELLS + 1U])
{
    for (uint8_t i = 0U; i < GAME_BOARD_CELLS; i++) {
        switch ((GamePlayer)s_board[i]) {
        case GAME_PLAYER_X: out[i] = 'X'; break;
        case GAME_PLAYER_O: out[i] = 'O'; break;
        default:            out[i] = '.'; break;
        }
    }
    out[GAME_BOARD_CELLS] = '\0';
}

/* ==========================================================================
 * Game engine — internal helpers
 * ========================================================================== */
static void reset_board(void)
{
    for (uint8_t i = 0U; i < GAME_BOARD_CELLS; i++) {
        s_board[i] = GAME_PLAYER_NONE;
    }
}

static GamePlayer opponent(GamePlayer p)
{
    return (p == GAME_PLAYER_X) ? GAME_PLAYER_O : GAME_PLAYER_X;
}

static GamePlayer find_winner(const uint8_t *board)
{
    static const uint8_t lines[8][3] = {
        {0,1,2}, {3,4,5}, {6,7,8},   /* rows      */
        {0,3,6}, {1,4,7}, {2,5,8},   /* columns   */
        {0,4,8}, {2,4,6}              /* diagonals */
    };
    for (uint8_t i = 0U; i < 8U; i++) {
        GamePlayer a = (GamePlayer)board[lines[i][0]];
        if (a != GAME_PLAYER_NONE &&
            a == (GamePlayer)board[lines[i][1]] &&
            a == (GamePlayer)board[lines[i][2]])
            return a;
    }
    return GAME_PLAYER_NONE;
}

static uint8_t board_full(const uint8_t *board)
{
    for (uint8_t i = 0U; i < GAME_BOARD_CELLS; i++) {
        if (board[i] == GAME_PLAYER_NONE) return 0U;
    }
    return 1U;
}
