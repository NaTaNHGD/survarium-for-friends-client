"""Single player executable; its runtime role retains the native guard until game exit."""
import sys


if __name__ == '__main__':
    if '--runtime' in sys.argv:
        sys.argv.remove('--runtime')
        from client_runtime import cli
        cli()
    else:
        from vps_launcher import main
        main()
