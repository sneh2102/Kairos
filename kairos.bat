@echo off
title Kairos
cd /d "%~dp0desktop"
if not exist node_modules call npm install
npm start
