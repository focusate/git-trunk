from distutils.core import setup
from git_trunk import __version__

setup(
    name='git_trunk',
    version=__version__,
    packages=['git_trunk'],
    license='LGPLv3',
    url='https://github.com/focusate/git-trunk',
    description="Git Trunk based workflow",
    long_description=open('README.rst').read(),
    install_requires=['footil>=0.24.0', 'gitpython'],
    scripts=['bin/git-trunk'],
    maintainer='Andrius Laukavičius',
    maintainer_email='dev@focusate.eu',
    python_requires='>=3.5',
    classifiers=[
        'Environment :: Other Environment',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Topic :: Software Development',
        'Topic :: Utilities',
    ],
)
